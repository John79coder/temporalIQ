# app/utils/endpoint_utils.py
import logging
from functools import wraps

import jwt  # Add PyJWT import
import requests
import wtforms.validators
from flask import request, g, current_app, jsonify, make_response
from flask_wtf.csrf import validate_csrf

from app.auth.models.entities import User
from app.utils.exceptions import (
    AuthError, ServiceUnavailableError, DatabaseError,
    wrap_external_error, format_error_response
)

def set_auth_cookies(response, access_token: str, refresh_token: str | None = None):
    """Set the HttpOnly access/refresh cookies. This is the sole auth transport —
    tokens are never included in the JSON response body."""
    cfg = current_app.config
    response.set_cookie(
        cfg["AUTH_COOKIE_NAME"], access_token,
        httponly=True, secure=cfg["AUTH_COOKIE_SECURE"], samesite=cfg["AUTH_COOKIE_SAMESITE"],
        domain=cfg.get("AUTH_COOKIE_DOMAIN"), max_age=cfg["JWT_EXP_HOURS"] * 3600, path="/",
    )
    if refresh_token:
        response.set_cookie(
            cfg["REFRESH_COOKIE_NAME"], refresh_token,
            httponly=True, secure=cfg["AUTH_COOKIE_SECURE"], samesite=cfg["AUTH_COOKIE_SAMESITE"],
            domain=cfg.get("AUTH_COOKIE_DOMAIN"), max_age=cfg["JWT_REFRESH_EXP_DAYS"] * 86400,
            path="/auth",  # scoped — only sent back on refresh/logout, not on every request
        )
    return response


def clear_auth_cookies(response):
    cfg = current_app.config
    response.set_cookie(cfg["AUTH_COOKIE_NAME"], "", expires=0, max_age=0, path="/",
                         secure=cfg["AUTH_COOKIE_SECURE"], samesite=cfg["AUTH_COOKIE_SAMESITE"],
                         domain=cfg.get("AUTH_COOKIE_DOMAIN"), httponly=True)
    response.set_cookie(cfg["REFRESH_COOKIE_NAME"], "", expires=0, max_age=0, path="/auth",
                         secure=cfg["AUTH_COOKIE_SECURE"], samesite=cfg["AUTH_COOKIE_SAMESITE"],
                         domain=cfg.get("AUTH_COOKIE_DOMAIN"), httponly=True)
    return response


def csrf_protected(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-CSRF-Token")
        try:
            validate_csrf(token)
        except wtforms.validators.ValidationError as e:
            logging.error(f"CSRF validation failed: {str(e)}")
            error_response, status_code = format_error_response(AuthError("Invalid CSRF token"), 403)
            return make_response(jsonify(error_response), status_code)
        return f(*args, **kwargs)

    return decorated


def verify_apple_jwt_token(token: str):
    try:
        with requests.Session() as session:
            jwks = session.get("https://appleid.apple.com/auth/keys").json()
        # Implement Apple JWT validation if needed
        raise NotImplementedError("Apple ID JWT validation requires PyJWT or external lib.")
    except requests.RequestException as e:
        raise wrap_external_error(e, ServiceUnavailableError, "Failed to fetch Apple JWKS")
    except Exception as e:
        raise wrap_external_error(e, AuthError, "Failed to verify Apple JWT")


def verify_jwt(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get(current_app.config.get("AUTH_COOKIE_NAME", "auth_token"))
        if not token:
            logging.error("Missing auth cookie")
            raise AuthError("Missing token")

        try:
            payload = jwt.decode(
                token,
                current_app.config["JWT_SECRET_KEY"],
                algorithms=[current_app.config.get("JWT_ALGORITHM", "HS256")]
            )
            # Backward-compat: tokens minted before this change have no "type" claim.
            # Reject only if a type is present and it's wrong (i.e. a refresh token
            # used where an access token belongs) — don't reject absence of the claim.
            if payload.get("type") not in (None, "access"):
                logging.error("Wrong token type presented as access token")
                raise AuthError("Invalid token type")
            sub = payload.get("sub")
            if not sub:
                logging.error("Missing 'sub' claim in JWT")
                raise AuthError("Invalid or missing 'sub' claim")
            try:
                g.user_id = int(sub)
            except (ValueError, TypeError):
                logging.error(f"Invalid 'sub' claim: {sub}")
                raise AuthError("Invalid 'sub' claim")

            if not hasattr(g, "db"):
                logging.error("Database context not initialized")
                raise DatabaseError("Database context not initialized")
            g.current_user = g.db.query(User).filter(User.id == g.user_id).first()
            if not g.current_user:
                logging.error(f"User with ID {g.user_id} not found")
                raise AuthError(f"User with ID {g.user_id} not found")
        except jwt.ExpiredSignatureError as e:
            logging.error("Token expired")
            raise wrap_external_error(e, AuthError, "Token expired")
        except jwt.InvalidTokenError as e:
            logging.error(f"Invalid token: {str(e)}")
            raise wrap_external_error(e, AuthError, "Invalid token")
        except Exception as e:
            logging.error(f"Unexpected error during JWT verification: {str(e)}")
            raise wrap_external_error(e, DatabaseError, "Failed to verify JWT")

        return f(*args, **kwargs)

    return decorated
