# app/utils/endpoint_utils.py
import logging
from datetime import datetime, timezone
from functools import wraps

import jwt
import requests
import wtforms.validators
from flask import request, g, current_app, jsonify, make_response
from flask_wtf.csrf import validate_csrf

from app.auth.models.entities import User
from app.utils.exceptions import (
    AuthError, ServiceUnavailableError, DatabaseError,
    wrap_external_error, format_error_response
)


def csrf_protected(f):
    """
    CSRF protection decorator - ENHANCED but FULLY COMPATIBLE
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-CSRF-Token")
        try:
            validate_csrf(token)
        except wtforms.validators.ValidationError as e:
            # ENHANCEMENT: Security logging (doesn't break existing code)
            logging.warning(f"CSRF validation failed for {request.endpoint}: {str(e)} - IP: {request.remote_addr}")
            error_response, status_code = format_error_response(AuthError("Invalid CSRF token"), 403)
            return make_response(jsonify(error_response), status_code)
        return f(*args, **kwargs)

    return decorated


def verify_jwt(f):
    """
    JWT verification decorator - ENHANCED but FULLY COMPATIBLE

    This maintains 100% compatibility with existing routes while adding
    security enhancements like token blacklisting when available.
    """

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
            # UNCHANGED: Decode JWT using PyJWT (maintains compatibility)
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

            # ENHANCEMENT: Token blacklist checking (only if service available)
            jwt_revocation_service = None
            try:
                if hasattr(current_app.extensions.get('app_context', {}), 'get_service'):
                    jwt_revocation_service = current_app.extensions['app_context'].get_service('jwt_revocation_service')
            except Exception as _:
                pass  # Service not available, continue without blacklist checking

            if jwt_revocation_service:
                # Check token-specific revocation
                jti = payload.get('jti')
                if jti and jwt_revocation_service.is_token_revoked(jti):
                    logging.warning(f"Revoked token used: {jti} for user {g.user_id}")
                    raise AuthError("Token has been revoked")

                # Check user-wide revocation
                iat = payload.get('iat')
                if iat:
                    token_issued_at = datetime.fromtimestamp(iat, timezone.utc)
                    if jwt_revocation_service.is_user_token_revoked(g.user_id, token_issued_at):
                        logging.warning(f"User {g.user_id} token issued before revocation timestamp")
                        raise AuthError("Token has been revoked")

            # UNCHANGED: Database user loading (maintains compatibility)
            if not hasattr(g, "db"):
                logging.error("Database context not initialized")
                raise DatabaseError("Database context not initialized")
            g.current_user = g.db.query(User).filter(User.id == g.user_id).first()
            if not g.current_user:
                logging.error(f"User with ID {g.user_id} not found")
                raise AuthError(f"User with ID {g.user_id} not found")

            # ENHANCEMENT: Verify that the account is still active (graceful)
            if not getattr(g.current_user, 'is_verified', True):
                logging.warning(f"Unverified user {g.user_id} attempted access")
                raise AuthError("Account not verified")

        except jwt.ExpiredSignatureError as e:
            logging.error("Token expired")
            raise wrap_external_error(e, AuthError, "Token expired")
        except jwt.InvalidTokenError as e:
            logging.error(f"Invalid token: {str(e)}")
            raise wrap_external_error(e, AuthError, "Invalid token")
        except AuthError:
            # Re-raise AuthError as-is (maintains compatibility)
            raise
        except Exception as e:
            logging.error(f"Unexpected error during JWT verification: {str(e)}")
            raise wrap_external_error(e, DatabaseError, "Failed to verify JWT")

        return f(*args, **kwargs)

    return decorated


def verify_apple_jwt_token(token: str):
    """
    Apple JWT token verification - UNCHANGED for compatibility
    """
    try:
        with requests.Session() as session:
            _ = session.get("https://appleid.apple.com/auth/keys").json()
        # Implement Apple JWT validation if needed
        raise NotImplementedError("Apple ID JWT validation requires PyJWT or external lib.")
    except requests.RequestException as e:
        raise wrap_external_error(e, ServiceUnavailableError, "Failed to fetch Apple JWKS")
    except Exception as e:
        raise wrap_external_error(e, AuthError, "Failed to verify Apple JWT")


# NEW FEATURES - These don't break existing code but add capabilities
def admin_required(f):
    """
    NEW: Admin access decorator - Use after @verify_jwt
    """

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
    """
    NEW: Enhanced rate limiting key function
    """
    if hasattr(g, 'user_id') and g.user_id:
        return f"user:{g.user_id}"

    from flask_limiter.util import get_remote_address
    return f"ip:{get_remote_address()}"


def record_login_attempt(email: str, success: bool, ip_address: str, user_id: int = None):
    """
    NEW: Record login attempts for security monitoring
    """
    try:
        login_service = current_app.extensions['app_context'].get_service('login_attempt_service')
        if login_service:
            login_service.record_login_attempt(email, success, ip_address, user_id=user_id)
    except Exception as e:
        logging.error(f"Failed to record login attempt: {str(e)}")
        # Don't fail the request if logging fails


def log_security_event(event_type: str, description: str, severity: str = "info",
                       user_id: int = None, additional_data: dict = None):
    """
    NEW: Log security events
    """
    try:
        security_service = current_app.extensions['app_context'].get_service('security_event_service')
        if security_service:
            security_service.log_security_event(
                event_type, description, severity, user_id, request.remote_addr, additional_data
            )
    except Exception as e:
        logging.error(f"Failed to log security event: {str(e)}")
        # Don't fail the request if logging fails