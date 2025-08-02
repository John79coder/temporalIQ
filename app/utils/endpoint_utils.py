# app/utils/endpoint_utils.py
from functools import wraps
import requests
import jwt  # Add PyJWT import
from flask import request, g, current_app, jsonify, make_response
from flask_wtf.csrf import validate_csrf
from app.auth.models.entities import User
from app.utils.exceptions import (
    AuthError, ServiceUnavailableError, DatabaseError,
    wrap_external_error, format_error_response
)
import wtforms.validators
import logging


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
        token = request.headers.get("Authorization")
        if not token:
            logging.error("Missing Authorization header")
            raise AuthError("Missing token")
        if token.lower().startswith("bearer "):
            token = token[len("Bearer "):].strip()
        else:
            logging.error("Invalid Authorization header format")
            raise AuthError("Invalid Authorization header format")

        try:
            # Decode JWT using PyJWT
            payload = jwt.decode(
                token,
                current_app.config["JWT_SECRET_KEY"],
                algorithms=[current_app.config.get("JWT_ALGORITHM", "HS256")]
            )
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