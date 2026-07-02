# app/auth/routes/api.py
import requests
from flask import Blueprint, request, jsonify, current_app, g, make_response, session
from flask_wtf.csrf import generate_csrf
from pydantic import ValidationError as PydanticValidationError

from app.auth.models.schemas import UserCreate, UserLogin, TokenSchema, UserOut
from app.extensions import limit, limiter, csrf_exempt

from app.utils.exceptions import DataValidationError, DatabaseError, AuthError, ServiceUnavailableError, \
    format_error_response

from app.utils.endpoint_utils import csrf_protected, set_auth_cookies, clear_auth_cookies, verify_jwt

import logging

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _serialize_user(user):
    """Serialize a User ORM object to a UserOut dict, with live 2FA status attached.

    UserOut.two_factor_enabled defaults to False and isn't populated by
    model_validate alone, so every route returning a user must go through
    this instead of calling UserOut.model_validate(user).model_dump() directly.
    """
    two_factor_service = current_app.extensions["app_context"].get_service("two_factor_service")
    user_out = UserOut.model_validate(user)
    user_out.two_factor_enabled = two_factor_service.status(g.db, user_out.id)["enabled"]
    return user_out.model_dump()


@bp.route("/signup", methods=["POST"])
@csrf_protected
@limiter.limit(limit("3 per minute"))
def signup():
    try:
        data = UserCreate(**request.json)
    except PydanticValidationError as e:

        logger.warning(
            "Signup request validation failed",
            extra={
                "event": "auth.signup.validation_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        user = authentication_service.create_user(g.db, data.email, data.password)
        email_verification_service = current_app.extensions['app_context'].get_service('email_verification_service')
        _ = email_verification_service.create_email_verification_token(g.db, user.id, data.email)

        g.db.commit()

        logger.info(
            "User account created",
            extra={
                "event": "auth.signup.success",
                "user_id": user.id,
            },
        )

        return jsonify({
            "message": "Account created. Please verify your email."
        }), 200

    except AuthError as e:

        logger.warning(
            "Signup rejected",
            extra={
                "event": "auth.signup.auth_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 401)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:

        logger.error(
            "Database error during signup",
            extra={
                "event": "auth.signup.database_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)
    except ServiceUnavailableError as e:

        logger.error(
            "Signup service unavailable",
            extra={
                "event": "auth.signup.service_unavailable",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/login", methods=["POST"])
@csrf_protected
@limiter.limit(limit("5 per minute"))
def login():

    try:
        data = UserLogin(**request.json)
    except PydanticValidationError as e:

        logger.warning(
            "Login request validation failed",
            extra={
                "event": "auth.login.validation_error",
                "error": str(e),
            },
        )

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
            logger.warning(
                "Invalid login credentials",
                extra={
                    "event": "auth.login.invalid_credentials",
                    "email": data.email,
                },
            )

            error_response, status_code = format_error_response(
                AuthError("Invalid email or password"),
                401,
            )
            return make_response(jsonify(error_response), status_code)

        if not user.is_verified:
            logger.warning(
                "Account not verified",
                extra={
                    "event": "auth.login.account_not_verified",
                    "user_id": user.id,
                },
            )

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

            logger.info(
                "Two-factor authentication required",
                extra={
                    "event": "auth.login.requires_two_factor",
                    "user_id": user.id,
                },
            )

            return jsonify(
                {
                    "requires_two_factor": True,
                    "user_id": user.id,
                }
            ), 200

        tokens = authentication_service.issue_token_pair(user.id)

        logger.info(
            "Login successful",
            extra={
                "event": "auth.login.success",
                "user_id": user.id,
            },
        )

        response = make_response(jsonify({
            "user": _serialize_user(user),
        }), 200)
        set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
        return response

    except AuthError as e:

        logger.warning(
            "Authentication failed",
            extra={
                "event": "auth.login.auth_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 401)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:

        logger.error(
            "Database error during login",
            extra={
                "event": "auth.login.database_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:

        logger.exception(
            "Unexpected exception during login",
            extra={
                "event": "auth.login.unexpected_exception",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(AuthError("Login failed"), 500)
        return make_response(jsonify(error_response), status_code)

@bp.route("/logout", methods=["POST"])
@csrf_protected
@limiter.limit(limit("10 per minute"))
def logout():
    try:
        session.clear()

        logger.info(
            "User logged out",
            extra={
                "event": "auth.logout.success",
            },
        )

        response = make_response(jsonify({"message": "Successfully logged out"}), 200)
        clear_auth_cookies(response)
        return response

    except Exception as e:

        logger.exception(
            "Unexpected exception during logout",
            extra={
                "event": "auth.logout.unexpected_exception",
                "error": str(e),
            },
        )

        response = make_response(
            jsonify({"message": "Logged out (client-side)"}),
            200,
        )
        clear_auth_cookies(response)
        return response


@bp.route("/refresh", methods=["POST"])
@csrf_protected
@limiter.limit(limit("20 per minute"))
def refresh():

    refresh_token = request.cookies.get(current_app.config["REFRESH_COOKIE_NAME"])
    if not refresh_token:

        logger.warning(
            "Refresh attempted without refresh cookie",
            extra={
                "event": "auth.refresh.missing_cookie",
            },
        )

        error_response, status_code = format_error_response(AuthError("Missing refresh token"), 401)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')

    try:
        user = authentication_service.verify_refresh_token(g.db, refresh_token)
        if not user.is_verified:
            raise AuthError("Account not verified")

        tokens = authentication_service.issue_token_pair(user.id)

        logger.info(
            "Token refreshed",
            extra={
                "event": "auth.refresh.success",
                "user_id": user.id,
            },
        )

        response = make_response(jsonify({"user": _serialize_user(user)}), 200)
        set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
        return response

    except AuthError as e:

        logger.warning(
            "Refresh token rejected",
            extra={
                "event": "auth.refresh.auth_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 401)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:

        logger.error(
            "Database error during refresh",
            extra={
                "event": "auth.refresh.database_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:

        logger.exception(
            "Unexpected exception during token refresh",
            extra={
                "event": "auth.refresh.unexpected_exception",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(
            AuthError("Token refresh failed"),
            500,
        )
        return make_response(jsonify(error_response), status_code)


@bp.route("/verify", methods=["POST"])
@csrf_protected
@limiter.limit(limit("5 per minute"))
def verify_email():
    try:
        data = TokenSchema(**request.json)

        logger.info(
            "Email verification attempt",
            extra={
                "event": "auth.email_verification.started",
                "token_prefix": data.token[:20] + "..." if data.token else None,
            },
        )

    except PydanticValidationError as e:

        logger.warning(
            "Email verification request validation failed",
            extra={
                "event": "auth.email_verification.validation_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    email_verification_service = current_app.extensions['app_context'].get_service('email_verification_service')
    try:
        vt = email_verification_service.verify_token(g.db, data.token)
        if not vt:

            logger.warning(
                "Email verification failed",
                extra={
                    "event": "auth.email_verification.invalid_token",
                    "token_prefix": data.token[:20] + "...",
                },
            )

            error_response, status_code = format_error_response(AuthError("Invalid or expired token"), 400)
            return make_response(jsonify(error_response), status_code)

        authentication_service = current_app.extensions['app_context'].get_service('authentication_service')

        user = authentication_service.user_repo.update_verified(g.db, vt.user_id)
        g.db.commit()

        tokens = authentication_service.issue_token_pair(user.id)

        logger.info(
            "Email verification successful",
            extra={
                "event": "auth.email_verification.success",
                "user_id": user.id,
            },
        )

        response = make_response(jsonify({
            "user": _serialize_user(user),
        }), 200)
        set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
        return response

    except DatabaseError as e:

        logger.error(
            "Database error during email verification",
            extra={
                "event": "auth.email_verification.database_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except ServiceUnavailableError as e:

        logger.error(
            "Email verification service unavailable",
            extra={
                "event": "auth.email_verification.service_unavailable",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:

        logger.exception(
            "Unexpected exception during email verification",
            extra={
                "event": "auth.email_verification.unexpected_exception",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(AuthError("Email verification failed"), 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/apple-signin", methods=["POST"])
@csrf_protected
@limiter.limit(limit("5 per minute"))
def apple_signin():

    id_token = request.json.get("id_token")

    if not id_token:
        logger.warning(
            "Apple Sign-In validation failed",
            extra={
                "event": "auth.apple_signin.validation_error",
                "error": "Missing id_token",
            },
        )

        error_response, status_code = format_error_response(
            DataValidationError("Missing id_token"),
            400,
        )
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
        user = authentication_service.authenticate_apple_user(
            g.db,
            id_token,
            jwks,
        )

        tokens = authentication_service.issue_token_pair(user.id)

        logger.info(
            "Apple Sign-In successful",
            extra={
                "event": "auth.apple_signin.success",
                "user_id": user.id,
            },
        )

        response = make_response(jsonify({
            "status": "success",
            "user": _serialize_user(user),
        }), 200)

        set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
        return response

    except requests.RequestException as e:

        current_app.extensions["app_context"].get_service(
            "caching_service"
        ).delete(jwks_cache_key)

        logger.error(
            "Failed to fetch Apple JWKS",
            extra={
                "event": "auth.apple_signin.jwks_fetch_failed",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(
            ServiceUnavailableError("Failed to fetch Apple JWKS"),
            500,
        )

        return make_response(jsonify(error_response), status_code)


    except AuthError as e:

        logger.warning(
            "Apple Sign-In rejected",
            extra={
                "event": "auth.apple_signin.auth_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 401)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:

        logger.error(
            "Database error during Apple Sign-In",
            extra={
                "event": "auth.apple_signin.database_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:

        logger.exception(
            "Unexpected exception during Apple Sign-In",
            extra={
                "event": "auth.apple_signin.unexpected_exception",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(
            AuthError("Apple Sign-In failed"),
            500,
        )
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

        logger.warning(
            "Password reset request validation failed",
            extra={
                "event": "auth.password_reset.validation_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        authentication_service.request_password_reset(g.db, email)

        logger.info(
            "Password reset requested",
            extra={
                "event": "auth.password_reset.requested",
                "email": email,
            },
        )

        return jsonify({"message": "Password reset link sent to your email"}), 200

    except AuthError as e:

        logger.warning(
            "Password reset request rejected",
            extra={
                "event": "auth.password_reset.auth_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:

        logger.error(
            "Database error during password reset request",
            extra={
                "event": "auth.password_reset.database_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
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

        logger.warning(
            "Password reset confirmation validation failed",
            extra={
                "event": "auth.password_reset.confirm.validation_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    authentication_service = current_app.extensions['app_context'].get_service('authentication_service')
    try:
        user = authentication_service.reset_password(g.db, token, new_password)
        tokens = authentication_service.issue_token_pair(user.id)

        response = make_response(jsonify({
            "user": _serialize_user(user),
        }), 200)
        set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])

        logger.info(
            "Password reset completed",
            extra={
                "event": "auth.password_reset.completed",
                "user_id": user.id,
            },
        )

        return response

    except AuthError as e:

        logger.warning(
            "Password reset confirmation rejected",
            extra={
                "event": "auth.password_reset.confirm.auth_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)
    except DatabaseError as e:

        logger.error(
            "Database error during password reset confirmation",
            extra={
                "event": "auth.password_reset.confirm.database_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

@bp.route("/csrf", methods=["GET"])
@csrf_exempt
def get_csrf_token():
    try:
        session["csrf_init"] = True

        token = generate_csrf()

        response = jsonify({"csrf_token": token})
        response.headers.set("X-CSRFToken", token)

        response.set_cookie(
            current_app.config["CSRF_COOKIE_NAME"],
            token,
            httponly=False,
            secure=current_app.config["AUTH_COOKIE_SECURE"],
            samesite=current_app.config["AUTH_COOKIE_SAMESITE"],
            path="/",
        )

        logger.info(
            "CSRF token generated",
            extra={
                "event": "auth.csrf.generated",
                "cookie_name": current_app.config["CSRF_COOKIE_NAME"],
                "secure": current_app.config["AUTH_COOKIE_SECURE"],
                "same_site": current_app.config["AUTH_COOKIE_SAMESITE"],
            },
        )

        return response, 200

    except Exception as e:
        logger.exception(
            "Unexpected exception while generating CSRF token",
            extra={
                "event": "auth.csrf.unexpected_exception",
                "error": str(e),
            },
        )
        raise


@bp.route("/me", methods=["GET"])
@verify_jwt
@limiter.limit(limit("60 per minute"))
def current_user():
    return jsonify({"user": _serialize_user(g.current_user)})