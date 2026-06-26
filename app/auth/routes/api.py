# app/auth/routes/api.py
from datetime import timedelta

import jwt
import requests
from flask import Blueprint, request, jsonify, current_app, g, make_response, session
from flask_wtf.csrf import generate_csrf
from pydantic import ValidationError as PydanticValidationError

from app.auth.models.schemas import UserCreate, UserLogin, TokenSchema, UserOut
from app.extensions import limit, limiter, csrf_exempt
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, DatabaseError, AuthError, ServiceUnavailableError, \
    format_error_response
from app.utils.time_zone import TimeZone

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/signup", methods=["POST"])
@csrf_protected
@limiter.limit(limit("3 per minute"))
def signup():
    try:
        data = UserCreate(**request.json)
    except PydanticValidationError as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        user = authentication_service.create_user(g.db, data.email, data.password)
        email_verification_service = current_app.extensions['app_context'].get_service('email_verification_service')
        _ = email_verification_service.create_email_verification_token(g.db, user.id, data.email)

        g.db.commit()

        return jsonify({
            "message": "Account created. Please verify your email."
        }), 200

    except AuthError as e:
        error_response, status_code = format_error_response(AuthError(str(e)), 401)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)
    except ServiceUnavailableError as e:
        error_response, status_code = format_error_response(ServiceUnavailableError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/login", methods=["POST"])
@csrf_protected
@limiter.limit(limit("5 per minute"))
def login():
    logging_service = current_app.extensions['app_context'].get_service('logging_service')

    try:
        data = UserLogin(**request.json)
    except PydanticValidationError as e:
        logging_service.error(f"Login validation error: {str(e)}")
        error_response, status_code = format_error_response(
            DataValidationError(str(e)),
            400,
        )
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions["app_context"].get_service(
        "authentication_service"
    )

    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        user = authentication_service.authenticate_user(
            g.db,
            data.email,
            data.password,
        )

        if not user:
            logging_service.error("Login failed: Invalid email or password",
                                 extra={"email": data.email})
            error_response, status_code = format_error_response(
                AuthError("Invalid email or password"),
                401,
            )
            return make_response(jsonify(error_response), status_code)

        if not user.is_verified:
            logging_service.error("Login failed: Account not verified",
                                 user_id=user.id)
            error_response, status_code = format_error_response(
                AuthError("Account not verified"),
                403,
            )
            return make_response(jsonify(error_response), status_code)

        # Check 2FA status
        two_factor_status = two_factor_service.status(
            g.db,
            user.id,
        )

        if two_factor_status["enabled"]:
            logging_service.info("Login requires 2FA", user_id=user.id)
            return jsonify(
                {
                    "requires_two_factor": True,
                    "user_id": user.id,
                }
            ), 200

        # Normal successful login (no 2FA)
        jwt_token = jwt.encode(
            {
                "sub": str(user.id),
                "exp": TimeZone.utc_now() + timedelta(hours=24),
            },
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"],
        )

        logging_service.info("Login successful (no 2FA)", user_id=user.id)

        return jsonify(
            {
                "user": UserOut.model_validate(user).model_dump(),
                "jwt": jwt_token,
            }
        ), 200

    except AuthError as e:
        logging_service.error(f"AuthError during login: {str(e)}")
        error_response, status_code = format_error_response(e, 401)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:
        logging_service.error(f"DatabaseError during login: {str(e)}")
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:
        logging_service.error(f"Unexpected error during login: {str(e)}")
        import traceback
        traceback.print_exc()
        error_response, status_code = format_error_response(AuthError("Login failed"), 500)
        return make_response(jsonify(error_response), status_code)

@bp.route("/logout", methods=["POST"])
@csrf_protected
@limiter.limit(limit("10 per minute"))
def logout():
    try:
        # Optional: Add server-side cleanup if we implement token-blacklisting later
        # For pure JWT, this is mostly a no-op on backend

        # Clear any session data if using Flask sessions
        session.clear()

        return jsonify({
            "message": "Successfully logged out"
        }), 200

    except Exception:
        return jsonify({
            "message": "Logged out (client-side)"
        }), 200


@bp.route("/verify", methods=["POST"])
@csrf_protected
@limiter.limit(limit("5 per minute"))
def verify_email():
    logging_service = current_app.extensions['app_context'].get_service('logging_service')

    try:
        data = TokenSchema(**request.json)
        logging_service.info("Email verification attempt", extra={"token_prefix": data.token[:20] + "..." if data.token else None})
    except PydanticValidationError as e:
        logging_service.error(f"Email verification validation error: {str(e)}")
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    email_verification_service = current_app.extensions['app_context'].get_service('email_verification_service')
    try:
        vt = email_verification_service.verify_token(g.db, data.token)
        if not vt:
            logging_service.error("Email verification failed: Invalid or expired token", extra={"token": data.token[:20] + "..."})
            error_response, status_code = format_error_response(AuthError("Invalid or expired token"), 400)
            return make_response(jsonify(error_response), status_code)

        authentication_service = current_app.extensions['app_context'].get_service('authentication_service')

        user = authentication_service.user_repo.update_verified(g.db, vt.user_id)
        g.db.commit()

        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )

        logging_service.info("Email verification successful", user_id=user.id)

        return jsonify({"user": UserOut.model_validate(user).model_dump(), "jwt": jwt_token}), 200

    except DatabaseError as e:
        logging_service.error(f"DatabaseError during email verification: {str(e)}")
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)

    except ServiceUnavailableError as e:
        logging_service.error(f"ServiceUnavailableError during email verification: {str(e)}")
        error_response, status_code = format_error_response(ServiceUnavailableError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:
        logging_service.error(f"Unexpected error during email verification: {str(e)}")
        import traceback
        traceback.print_exc()
        error_response, status_code = format_error_response(AuthError("Email verification failed"), 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/apple-signin", methods=["POST"])
@csrf_protected
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


@bp.route("/reset-password", methods=["POST"])
@csrf_protected
@limiter.limit(limit("3 per minute"))
def request_password_reset():
    try:
        data = request.json
        email = data.get("email")
        if not email:
            raise DataValidationError("Missing email")
    except Exception as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        authentication_service.request_password_reset(g.db, email)
        return jsonify({"message": "Password reset link sent to your email"}), 200
    except AuthError as e:
        error_response, status_code = format_error_response(AuthError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/reset-password/confirm", methods=["POST"])
@csrf_protected
@limiter.limit(limit("5 per minute"))
def confirm_password_reset():
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
        user = authentication_service.reset_password(g.db, token, new_password)
        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )
        return jsonify({"user": UserOut.model_validate(user).model_dump(), "jwt": jwt_token}), 200
    except AuthError as e:
        error_response, status_code = format_error_response(AuthError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:
        error_response, status_code = format_error_response(DatabaseError(str(e)), 500)
        return make_response(jsonify(error_response), status_code)

@bp.route("/csrf", methods=["GET"])
@csrf_exempt
def get_csrf_token():
    session["csrf_init"] = True

    token = generate_csrf()

    print("\n===== /auth/csrf =====")
    print("Session SID:", getattr(session, "sid", "<no sid>"))
    print("Session contents:", dict(session))
    print("======================\n")

    response = jsonify({"csrf_token": token})
    response.headers.set("X-CSRFToken", token)
    return response, 200