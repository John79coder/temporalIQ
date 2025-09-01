# app/auth/routes/api.py
from datetime import timedelta
import uuid

import jwt
import requests
from flask import Blueprint, request, jsonify, current_app, g, make_response, session
from flask_session import Session
from flask_wtf.csrf import generate_csrf
from pydantic import ValidationError as PydanticValidationError

from app.auth.email_verification.service import EmailVerificationService
from app.auth.models.schemas import UserCreate, UserLogin, TokenSchema, UserOut
from app.extensions import limit, limiter, csrf_exempt
from app.utils.db_transactions import transactional_route
from app.utils.endpoint_utils import verify_jwt
from app.utils.exceptions import DataValidationError, DatabaseError, AuthError, ServiceUnavailableError, \
    format_error_response
from app.utils.time_zone import TimeZone

bp = Blueprint("auth", __name__, url_prefix="/auth")


def log_request_details(endpoint_name):
    """Helper to log detailed request information"""
    print(f"\n{'=' * 60}")
    print(f"[{endpoint_name}] REQUEST DETAILS")
    print(f"{'=' * 60}")
    print(f"Method: {request.method}")
    print(f"URL: {request.url}")
    print(f"Origin: {request.headers.get('Origin', 'No Origin header')}")
    print(f"Host: {request.headers.get('Host', 'No Host header')}")
    print(f"Referer: {request.headers.get('Referer', 'No Referer')}")

    # Log all cookies received
    print(f"\nCookies Received ({len(request.cookies)} total):")
    for cookie_name, cookie_value in request.cookies.items():
        print(f"  - {cookie_name}: {cookie_value[:50]}..." if len(
            cookie_value) > 50 else f"  - {cookie_name}: {cookie_value}")

    # Log session details
    print(f"\nSession Details:")

    sid = getattr(session, "sid", None)
    print(f"  Session SID: {sid or 'NO SID'}")
    print(f"  Session ID (_id): {session.get('_id', 'NO _id')}")

    print(f"  Session New: {session.new if hasattr(session, 'new') else 'Unknown'}")
    print(f"  Session Modified: {session.modified if hasattr(session, 'modified') else 'Unknown'}")
    print(f"  Session Permanent: {session.permanent}")
    print(f"  Session Keys: {list(session.keys())}")
    if 'csrf_token' in session:
        print(f"  CSRF in session: {session['csrf_token'][:20]}...")

    # Log CORS-related headers
    print(f"\nCORS Headers in Request:")
    for header in ['Access-Control-Request-Method', 'Access-Control-Request-Headers',
                   'Access-Control-Allow-Credentials']:
        print(f"  {header}: {request.headers.get(header, 'Not present')}")

    # Check Redis if using Redis sessions
    if hasattr(current_app, 'session_interface'):
        si = current_app.session_interface
        if hasattr(si, 'redis'):
            try:
                if sid:
                    redis_key = f"{si.key_prefix}{sid}"
                    redis_value = si.redis.get(redis_key)
                    print("\nRedis Check:")
                    print(f"  Key: {redis_key}")
                    print(f"  Exists in Redis: {redis_value is not None}")
                    print(f"  Value (prefix): {(redis_value[:50] + b'...') if redis_value else None}")
            except Exception as e:
                print(f"  Redis check error: {e}")

    # Log headers
    print(f"\nRequest Headers:")
    for header_name, header_value in request.headers.items():
        print(f"  {header_name}: {header_value}")

    # Log body if POST/PUT
    if request.method in ["POST", "PUT"]:
        try:
            body = request.get_json() or request.form or request.data
            print(f"\nRequest Body: {body}")
        except Exception as e:
            print(f"\nRequest Body: <error reading: {e}>")

    print(f"{'=' * 60}\n")


def log_response_details(endpoint_name, response):
    """Helper to log response details"""
    print(f"\n{'=' * 60}")
    print(f"[{endpoint_name}] RESPONSE DETAILS")
    print(f"{'=' * 60}")
    print(f"Status: {response.status_code}")

    # Log response headers
    print(f"\nResponse Headers:")
    for header_name, header_value in response.headers.items():
        print(f"  {header_name}: {header_value}")

    print(f"{'=' * 60}\n")


@bp.route("/csrf", methods=["GET"])
@csrf_exempt
@limiter.limit("5/minute")
def get_csrf_token():
    """Generate and return a new CSRF token for frontend"""
    log_request_details("GET_CSRF")

    # Force a completely new session
    from flask import session as flask_session

    # Clear any existing session
    # flask_session.clear()

    # Create new session ID
    flask_session['_id'] = str(uuid.uuid4())
    flask_session['initialized'] = True
    flask_session['created_at'] = str(TimeZone.utc_now())

    # Generate CSRF token - this should also modify session
    token = generate_csrf()

    # Force the permanent flag
    flask_session.permanent = True  # This triggers TTL in Redis
    flask_session.modified = True

    # Try to force save
    # if hasattr(current_app, 'session_interface'):
    #     current_app.session_interface.should_set_cookie = lambda app, session: True

    response = make_response(jsonify({
        "csrf_token": token,
        "debug": {
            "session_id": flask_session.get('_id'),
            "session_keys": list(flask_session.keys()),
            "modified": flask_session.modified,
        }
    }))

    # CRITICAL: Manually save the session
    current_app.session_interface.save_session(current_app, flask_session, response)

    # Add CORS headers
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', 'http://localhost:3000')
    response.headers['Access-Control-Allow-Credentials'] = 'true'

    return response


@bp.route("/csrf", methods=["OPTIONS"])
@csrf_exempt
def csrf_options():
    """Handle OPTIONS preflight for /csrf"""
    response = make_response()
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', 'http://localhost:3000')
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRF-Token, X-CSRFToken, X-Request-ID'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


@bp.route("/signup", methods=["POST"])
@limiter.limit(limit("3 per minute"))
@transactional_route()
def signup(db: Session):

    try:
        data = UserCreate(**request.json)

    except PydanticValidationError as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')

    try:
        user = authentication_service.create_user(g.db, data.email, data.password)
        email_verification_service = current_app.extensions['app_context'].get_service('email_verification_service')
        email_verification_token = email_verification_service.create_email_verification_token(g.db, user.id, data.email)


        entitlements_service = current_app.extensions['app_context'].get_service('entitlements_service')
        entitlements_service.start_reverse_trial(g.db, user.id, tier='pro', days=14)

        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )

        return jsonify({"user": UserOut.model_validate(user).model_dump(), "jwt": jwt_token,
                        "token": email_verification_token.token,
                        "trial_info": {"tier": "pro", "days": 14,
                                       "ends_at": (TimeZone.utc_now() + timedelta(days=14)).isoformat()}}), 200
    except AuthError as e:
        error_response, status_code = format_error_response(AuthError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)
    except ServiceUnavailableError as e:
        error_response, status_code = format_error_response(ServiceUnavailableError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)


from flask import request, session, jsonify, current_app


@bp.route("/debug-cookies", methods=["GET", "OPTIONS"])
@csrf_exempt
def debug_cookies():
    """Debug endpoint to check cookie/session state"""
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', 'http://localhost:3000')
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    log_request_details("DEBUG-COOKIES")

    response = jsonify({
        "cookies_received": {name: value[:20] + "..." if len(value) > 20 else value
                             for name, value in request.cookies.items()},
        "session_data": {
            "id": session.get('_id', session.sid if hasattr(session, 'sid') else 'NO SESSION'),
            "keys": list(session.keys()),
            "new": session.new if hasattr(session, 'new') else None,
            "permanent": session.permanent
        },
        "headers": {
            "origin": request.headers.get('Origin'),
            "host": request.headers.get('Host'),
            "cookie": request.headers.get('Cookie', 'No Cookie header')[:100]
        },
        "cookie_keys_seen": list(request.cookies.keys()),
        "session_cookie_name": current_app.config.get("SESSION_COOKIE_NAME"),
        "session_sid": getattr(session, "sid", None),
        "session_has_token": "csrf_token" in session,
        "session_keys": list(dict(session).keys()),
    })

    # Add CORS headers
    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', 'http://localhost:3000')
    response.headers['Access-Control-Allow-Credentials'] = 'true'

    log_response_details("DEBUG-COOKIES", response)
    return response, 200


@bp.route("/set-session-test", methods=["GET"])
@csrf_exempt
def set_session_test():
    from flask import session, jsonify, current_app
    session["__smoke__"] = "ok"
    session.modified = True
    resp = jsonify({"wrote": "__smoke__"})
    current_app.session_interface.save_session(current_app, session, resp)  # force write
    return resp, 200


@bp.route("/get-session-test", methods=["GET"])
@csrf_exempt
def get_session_test():
    from flask import session, jsonify
    return jsonify({
        "sid": getattr(session, "sid", None),
        "keys": list(dict(session).keys()),
        "has_smoke": "__smoke__" in session
    }), 200


@bp.route("/login", methods=["POST"])
@limiter.limit(limit("5 per minute"))
def login():
    try:
        data = UserLogin(**request.json)
    except PydanticValidationError as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        user = authentication_service.authenticate_user(g.db, data.email, data.password)
        if not user:
            error_response, status_code = format_error_response(AuthError("Invalid email or password"), 401)
            return make_response(jsonify(error_response), status_code)
        if not user.is_verified:
            error_response, status_code = format_error_response(AuthError("Account not verified"), 403)
            return make_response(jsonify(error_response), status_code)
        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )
        return jsonify({"user": UserOut.model_validate(user).model_dump(), "jwt": jwt_token}), 200
    except AuthError as e:
        error_response, status_code = format_error_response(AuthError(str(e)), 401)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/verify", methods=["POST"])
@limiter.limit(limit("5 per minute"))
@transactional_route()
def verify_email(db: Session):
    try:
        data = TokenSchema(**request.json)

    except PydanticValidationError as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    email_verification_service = current_app.extensions['app_context'].get_service('email_verification_service')

    try:
        verification_token = email_verification_service.verify_token(g.db, data.token)

        if not verification_token:
            error_response, status_code = format_error_response(AuthError("Invalid or expired token"), 400)
            return make_response(jsonify(error_response), status_code)

        authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
        user = authentication_service.update_verified(g.db, verification_token.user_id)

        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )

        return jsonify({"user": UserOut.model_validate(user).model_dump(), "jwt": jwt_token}), 200

    except DatabaseError as e:
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)
    except ServiceUnavailableError as e:
        error_response, status_code = format_error_response(ServiceUnavailableError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)


# ADD: Resend verification endpoint (missing from original)
@bp.route("/resend-verification", methods=["POST", "OPTIONS"])
@limiter.limit(limit("5 per minute"))
def resend_verification():
    """Resend verification email to user"""
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', 'http://localhost:3000')
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRF-Token, X-CSRFToken, X-Request-ID'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    try:
        data = request.get_json()
        if not data or 'email' not in data:
            raise DataValidationError("Email is required")

        email = data['email']

        # Get services
        authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
        email_verification_service = current_app.extensions['app_context'].get_service('email_verification_service')

        # Find user by email
        user = authentication_service.user_repo.get_by_email(g.db, email)
        if not user:
            # Don't reveal if email exists or not for security
            return jsonify({"message": "If an account exists with this email, a verification link has been sent."}), 200

        # Check if already verified
        if user.is_verified:
            return jsonify({"message": "Account is already verified."}), 200

        # Generate a new verification token and send email
        EmailVerificationService.create_email_verification_token(g.db, user.id, user.email)

        return jsonify({"message": "Verification email sent. Please check your inbox."}), 200

    except PydanticValidationError as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)
    except DataValidationError as e:
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)
    except ServiceUnavailableError as e:
        error_response, status_code = format_error_response(e, 503)
        return make_response(jsonify(error_response), status_code)
    except Exception as e:
        # Log error but don't expose details
        current_app.logger.error(f"Error in resend_verification: {str(e)}")
        return jsonify({"message": "If an account exists with this email, a verification link has been sent."}), 200


# UPDATE: Add alias route for frontend compatibility
@bp.route("/request-reset", methods=["POST", "OPTIONS"])
@limiter.limit(limit("3 per minute"))
def request_password_reset_alias():
    """Alias for /reset-password to match frontend expectations"""
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', 'http://localhost:3000')
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRF-Token, X-CSRFToken, X-Request-ID'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    # Call the existing function
    return request_password_reset()


@bp.route("/reset-password", methods=["POST", "OPTIONS"])
@limiter.limit(limit("3 per minute"))
@transactional_route()
def request_password_reset(db: Session):
    """Request password reset - original endpoint kept for backwards compatibility"""
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', 'http://localhost:3000')
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRF-Token, X-CSRFToken, X-Request-ID'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    try:
        data = request.get_json()
        email = data.get("email")

        # Check if this is actually a reset confirmation (has token and new_password)
        if data.get("token") and data.get("new_password"):
            # This is actually a reset confirmation, redirect to that handler
            return confirm_password_reset()

        if not email:
            raise DataValidationError("Email is required")
    except Exception as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')

    # Always return a success message for security (don't reveal if email exists)
    try:
        user = authentication_service.user_repo.get_by_email(db, email)
        if user and user.is_verified:
            # Only send reset email if user exists and is verified
            authentication_service.request_password_reset(db, email)
    except Exception as e:
        # Log the error but don't expose it to the user
        current_app.logger.error(f"Error in password reset request: {str(e)}")

    # Always return the same message regardless of whether email exists
    return jsonify({"message": "If an account exists with this email, a password reset link has been sent."}), 200


@bp.route("/reset-password/confirm", methods=["POST"])
@limiter.limit(limit("5 per minute"))
@transactional_route()
def confirm_password_reset(db: Session):
    try:
        data = request.json


        token = data.get("token")
        new_password = data.get("new_password")
        if not token or not new_password:
            raise DataValidationError("Missing token or new_password")
    except Exception as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        user = authentication_service.reset_password(db, token, new_password)
        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )
        return jsonify({
            "message": "Password reset successful",
            "user": UserOut.model_validate(user).model_dump(),
            "jwt": jwt_token
        }), 200
    except AuthError as e:
        error_response, status_code = format_error_response(AuthError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/apple-signin", methods=["POST"])
@limiter.limit(limit("5 per minute"))
def apple_signin():
    id_token = request.json.get("id_token")
    if not id_token:
        error_response, status_code = format_error_response(DataValidationError("Missing id_token"), 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        jwks_cache_key = "auth:apple:jwks"
        jwks = current_app.extensions['app_context'].get_service('caching_service').get(jwks_cache_key)
        if not jwks:
            with requests.Session() as session:
                jwks = session.get("https://appleid.apple.com/auth/keys").json()
            current_app.extensions['app_context'].get_service('caching_service').set(jwks_cache_key, jwks,
                                                                                     timeout=604800)
        user = authentication_service.authenticate_apple_user(g.db, id_token, jwks)
        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )
        return jsonify({"status": "success", "user": UserOut.model_validate(user).model_dump(), "jwt": jwt_token}), 200
    except requests.RequestException:
        current_app.extensions['app_context'].get_service('caching_service').delete(jwks_cache_key)
        error_response, status_code = format_error_response(ServiceUnavailableError("Failed to fetch Apple JWKS"), 500)
        return make_response(jsonify(error_response), status_code)
    except (AuthError, DatabaseError) as e:
        error_response, status_code = format_error_response(e, 401 if isinstance(e, AuthError) else 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/onboarding", methods=["GET"])
@limiter.exempt()
def onboarding():
    cache_key = "auth:onboarding"
    try:
        cached_response = current_app.extensions['app_context'].get_service('caching_service').get(cache_key)
        if cached_response:
            return jsonify(cached_response)
        response = {
            "steps": [
                {"step": 1, "title": "Sign Up", "description": "Create an account with email and password."},
                {"step": 2, "title": "Verify Email", "description": "Check your inbox for a verification link."},
                {"step": 3, "title": "Connect Notion", "description": "Link your Notion workspace to import tasks."},
                {"step": 4, "title": "Connect iCloud", "description": "Link your iCloud calendar for scheduling."},
                {"step": 5, "title": "Review Schedule", "description": "Approve suggested time blocks."}
            ]
        }
        current_app.extensions['app_context'].get_service('caching_service').set(cache_key, response,
                                                                                 timeout=2592000)  # 30 days
        return jsonify(response)
    except ServiceUnavailableError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/test-session", methods=["POST"])
@csrf_exempt
def test_session_setup():
    try:
        token = generate_csrf()
        return jsonify({"csrf_token": token})
    except RuntimeError:
        error_response, status_code = format_error_response(ServiceUnavailableError("Failed to generate CSRF token"),
                                                            500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/2fa/setup", methods=["GET"])
@verify_jwt
@limiter.limit(limit("5 per minute"))
def setup_2fa():
    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        data = authentication_service.setup_2fa(g.db, g.current_user.id)
        return jsonify(data), 200
    except AuthError as e:
        error_response, status_code = format_error_response(AuthError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)
    except Exception as e:
        error_response, status_code = format_error_response(AuthError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/2fa/verify", methods=["POST"])
@limiter.limit(limit("5 per minute"))
def verify_2fa():
    data = request.json
    user_id = data.get("user_id")
    code = data.get("code")
    if not user_id or not code:
        error_response, status_code = format_error_response(DataValidationError("Missing user_id or code"), 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        if authentication_service.verify_2fa_code(g.db, user_id, code):
            user = authentication_service.user_repo.get_by_id(g.db, user_id)
            jwt_token = jwt.encode(
                {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
                current_app.config["JWT_SECRET_KEY"],
                algorithm=current_app.config["JWT_ALGORITHM"]
            )
            return jsonify({"jwt": jwt_token}), 200
        else:
            raise AuthError("Invalid 2FA code")
    except AuthError as e:
        error_response, status_code = format_error_response(AuthError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)