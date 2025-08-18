# app/auth/routes/api.py
from datetime import timedelta

import jwt
import requests
from flask import Blueprint, request, jsonify, current_app, g, make_response
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
        email_verification_token = email_verification_service.create_email_verification_token(g.db, user.id, data.email)

        # NEW: Start 14-day Pro reverse trial
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
@csrf_protected
@limiter.limit(limit("5 per minute"))
def verify_email():
    try:
        data = TokenSchema(**request.json)
    except PydanticValidationError as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    email_verification_service = current_app.extensions['app_context'].get_service('email_verification_service')
    try:
        vt = email_verification_service.verify_token(g.db, data.token)
        if not vt:
            error_response, status_code = format_error_response(AuthError("Invalid or expired token"), 400)
            return make_response(jsonify(error_response), status_code)
        authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
        user = authentication_service.user_repo.update_verified(g.db, vt.user_id)
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


@bp.route("/2fa/setup", methods=["GET"])
@verify_jwt
@csrf_protected
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
@csrf_protected
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
