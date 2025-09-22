# app/utils/endpoint_utils.py
import logging
from functools import wraps

import jwt
import requests
from flask import current_app, g, request

from app.utils.exceptions import AuthError, ServiceUnavailableError, wrap_external_error


def csrf_protected(f):
    """
    Decorator to protect endpoints with CSRF validation
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_app.config.get("WTF_CSRF_ENABLED", True):
            return f(*args, **kwargs)

        from flask_wtf.csrf import validate_csrf
        try:
            validate_csrf(request.headers.get("X-CSRF-Token") or request.form.get("csrf_token"))
        except Exception as e:
            logging.error(f"CSRF validation failed: {str(e)}")
            raise AuthError("Invalid CSRF token")

        return f(*args, **kwargs)

    return decorated


def verify_jwt(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logging.info("Starting JWT verification")

        token = None

        # Try cookie first (more secure)
        if 'auth_token' in request.cookies:
            token = request.cookies.get('auth_token')
            logging.info("Found token in cookie")
        # Fall back to Authorization header for backward compatibility
        elif 'Authorization' in request.headers:
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                logging.error("Invalid Authorization header format")
                raise AuthError("Invalid Authorization header format")
            token = auth_header.split(' ')[1]
            logging.info("Found token in Authorization header")

        if not token:
            logging.error("No authentication token provided")
            raise AuthError("No authentication token provided")

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

            # IMPORTANT: Check if session already exists from transactional_route
            if not hasattr(g, "db"):
                # Only create a new session if one doesn't exist
                from app.extensions import db
                g.db = db.session()

            # Load user with existing session
            from app.auth.models.entities import User
            g.current_user = g.db.query(User).filter(User.id == g.user_id).first()
            if not g.current_user:
                logging.error(f"User with ID {g.user_id} not found")
                raise AuthError(f"User with ID {g.user_id} not found")

            # Verify that the account is still active
            if not getattr(g.current_user, 'is_verified', True):
                logging.warning(f"Unverified user {g.user_id} attempted access")
                raise AuthError("Account not verified")

        except jwt.ExpiredSignatureError as e:
            logging.error("Token expired")
            raise AuthError("Token expired")
        except jwt.InvalidTokenError as e:
            logging.error(f"Invalid token: {str(e)}")
            raise AuthError("Invalid token")
        except AuthError:
            raise
        except Exception as e:
            logging.error(f"Unexpected error during JWT verification: {str(e)}")
            raise AuthError("Unexpected authentication error")

        return f(*args, **kwargs)

    return decorated_function

def verify_apple_jwt_token(token: str):
    """
    Apple JWT token verification
    """
    try:
        with requests.Session() as session:
            response = session.get("https://appleid.apple.com/auth/keys")
            response.raise_for_status()
            # Implement Apple JWT validation if needed
            raise NotImplementedError("Apple ID JWT validation requires implementation")
    except requests.RequestException as e:
        raise wrap_external_error(e, ServiceUnavailableError, "Failed to fetch Apple JWKS")
    except Exception as e:
        raise wrap_external_error(e, AuthError, "Failed to verify Apple JWT")


# Additional helper functions
def admin_required(f):
    """Admin access decorator - Use after @verify_jwt"""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(g, 'current_user') or not g.current_user:
            raise AuthError("Authentication required")

        if not getattr(g.current_user, 'is_admin', False):
            logging.warning(f"Non-admin user {g.current_user.id} attempted admin access to {request.endpoint}")
            raise AuthError("Administrative privileges required")

        return f(*args, **kwargs)

    return decorated


def get_enhanced_rate_limit_key():
    """Enhanced rate limiting key function"""
    if hasattr(g, 'user_id') and g.user_id:
        return f"user:{g.user_id}"

    from flask_limiter.util import get_remote_address
    return f"ip:{get_remote_address()}"