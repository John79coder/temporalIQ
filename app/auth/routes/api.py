# app/auth/routes/api.py
from flask import Blueprint, request, jsonify, current_app, g, abort, make_response
from flask_wtf.csrf import generate_csrf
from pydantic_core import ValidationError as PydanticValidationError
import jwt
from app.auth.models.schemas import UserCreate, UserOut, UserLogin, TokenSchema
from app.extensions import limit, limiter, csrf
from app.utils.endpoint_utils import csrf_protected
from app.utils.exceptions import DataValidationError, ServiceUnavailableError, AuthError, DatabaseError, \
    format_error_response
from datetime import timedelta
import requests
from app.utils.time_zone import TimeZone

bp = Blueprint("auth", __name__)

@bp.route("/auth/signup", methods=["POST"])
@csrf_protected
@limiter.limit(limit("3 per minute"))
def signup():
    try:
        user_data = UserCreate(**request.json)
    except PydanticValidationError as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    try:
        new_user = current_app.extensions['app_context'].get_service('authentication_service').create_user(g.db,
                                                                                                           str(user_data.email),
                                                                                                           user_data.password)
        email_verification_token = current_app.extensions['app_context'].get_service(
            'email_verification_service').create_email_verification_token(g.db, new_user.id, str(user_data.email))
        jwt_token = jwt.encode(
            {"sub": str(new_user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )
        return jsonify({
            "user": UserOut.model_validate(new_user).model_dump(),
            "token": email_verification_token.token,
            "jwt": jwt_token
        })
    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)
    except ServiceUnavailableError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

@bp.route("/auth/login", methods=["POST"])
@csrf_protected
@limiter.limit(limit("5 per minute"))
def login():
    try:
        data = UserLogin(**request.json)
    except PydanticValidationError as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    try:
        user = current_app.extensions['app_context'].get_service('authentication_service').authenticate_user(g.db,
                                                                                                             str(data.email),
                                                                                                             data.password)
        if not user:
            error_response, status_code = format_error_response(AuthError("Invalid credentials"), 401)
            return make_response(jsonify(error_response), status_code)
        if not user.is_verified:
            error_response, status_code = format_error_response(AuthError("Account not verified"), 403)
            return make_response(jsonify(error_response), status_code)
        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )
        return jsonify({
            "user": UserOut.model_validate(user).model_dump(),
            "jwt": jwt_token
        })
    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

@bp.route("/auth/verify", methods=["POST"])
@csrf_protected
@limiter.exempt()
def verify_email():
    try:
        data = TokenSchema(**request.get_json())
    except PydanticValidationError as e:
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_response(jsonify(error_response), status_code)

    try:
        vt = current_app.extensions['app_context'].get_service('email_verification_service').verify_token(g.db, data.token)
        if not vt:
            error_response, status_code = format_error_response(AuthError("Invalid or expired token"), 400)
            return make_response(jsonify(error_response), status_code)
        user = current_app.extensions['app_context'].get_service('authentication_service').user_repo.update_verified(
            g.db, vt.user_id)
        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )
        return jsonify({
            "user": UserOut.model_validate(user).model_dump(),
            "jwt": jwt_token
        })
    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)
    except ServiceUnavailableError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

@bp.route("/auth/apple-signin", methods=["POST"])
@csrf_protected
@limiter.limit(limit("5 per minute"))
def apple_signin():
    token = request.json.get("id_token")

    if not token:
        error_response, status_code = format_error_response(DataValidationError("Missing id_token"), 400)
        return make_response(jsonify(error_response), status_code)

    try:
        jwks_cache_key = "auth:apple:jwks"
        jwks = current_app.extensions['app_context'].get_service('caching_service').get(jwks_cache_key)
        if not jwks:
            with requests.Session() as session:
                jwks = session.get("https://appleid.apple.com/auth/keys").json()
            current_app.extensions['app_context'].get_service('caching_service').set(jwks_cache_key, jwks,
                                                                                     timeout=604800)
        user = current_app.extensions['app_context'].get_service('authentication_service').authenticate_apple_user(g.db,
                                                                                                                   token,
                                                                                                                   jwks)
        if not user:
            error_response, status_code = format_error_response(AuthError("Apple authentication failed"), 401)
            return make_response(jsonify(error_response), status_code)
        jwt_token = jwt.encode(
            {"sub": str(user.id), "exp": TimeZone.utc_now() + timedelta(hours=24)},
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"]
        )
        return jsonify({
            "status": "ok",
            "user": UserOut.model_validate(user).model_dump(),
            "jwt": jwt_token
        })
    except requests.RequestException:
        current_app.extensions['app_context'].get_service('caching_service').delete(jwks_cache_key)
        error_response, status_code = format_error_response(ServiceUnavailableError("Failed to fetch Apple JWKS"), 500)
        return make_response(jsonify(error_response), status_code)
    except (AuthError, DatabaseError) as e:
        error_response, status_code = format_error_response(e, 401 if isinstance(e, AuthError) else 500)
        return make_response(jsonify(error_response), status_code)

@bp.route("/auth/onboarding", methods=["GET"])
@limiter.exempt()
def onboarding():
    cache_key = "auth:onboarding"

    try:
        cached_response = current_app.extensions['app_context'].get_service('caching_service').get(cache_key)
        if cached_response:
            return jsonify(cached_response)

        response = {
            "steps": [
                {"step": 1, "title": "Sign Up", "description": "Create an account with your email and password."},
                {"step": 2, "title": "Verify Email", "description": "Check your inbox for a verification link."},
                {"step": 3, "title": "Connect Notion", "description": "Link your Notion workspace to import tasks."},
                {"step": 4, "title": "Connect iCloud", "description": "Link your iCloud calendar for scheduling."},
                {"step": 5, "title": "Review Schedule", "description": "Approve suggested time blocks."}
            ]
        }
        current_app.extensions['app_context'].get_service('caching_service').set(
            cache_key,
            response,
            timeout=2592000  # 30 days
        )
        return jsonify(response)

    except ServiceUnavailableError as e:
        return make_response(jsonify(format_error_response(e, 500)))

@bp.route("/auth/test-session", methods=["POST"])
@csrf.exempt
def test_session_setup():

    try:
        token = generate_csrf()
        return jsonify({"csrf_token": token})

    except RuntimeError:
        error_response, status_code = format_error_response(
            ServiceUnavailableError("Failed to generate CSRF token"),
            500)
        return make_response(jsonify(error_response), status_code)