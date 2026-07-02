# app/auth/session_manager/service.py
import logging
import pickle
import secrets
import smtplib
from datetime import timedelta
from typing import Optional

import jwt
import requests
from flask import current_app
from flask_mail import Message
from sqlalchemy.orm.session import Session
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.auth.models.entities import User
from app.auth.session_manager.repository import UserRepository
from app.features.services.service import FeaturesService
from app.utils.caching import ICacheService
from app.utils.exceptions import AuthError, DatabaseError, wrap_external_error, ServiceUnavailableError
from app.utils.security import pwd_context
from app.utils.time_zone import TimeZone
from config import Config


class AuthenticationService:
    def __init__(self, user_repo: UserRepository, caching_service: ICacheService, features_service: FeaturesService):
        self.user_repo = user_repo
        self.caching_service = caching_service
        self.features_service = features_service
        self.apple_jwks_url = "https://appleid.apple.com/auth/keys"
        self.failed_login_threshold = 5  # Configurable if needed

    def update_verified(self, db: Session, user_id: int) -> Optional[User]:
        try:
            user = self.user_repo.update_verified(db, user_id)
            if not user:
                raise AuthError("User not found")

            # Invalidate cache after successful update
            self.caching_service.delete(f"auth:user:email:{user.email}")

            return user
        except AuthError as e:
            raise
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to update user verification status")

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        try:
            return pwd_context.verify(plain, hashed)
        except (ValueError, TypeError) as e:
            logging.warning(f"Password verification failed due to invalid input: {str(e)}")
            return False
        except Exception as e:
            raise wrap_external_error(e, AuthError, "Password verification failed")

    def create_user(self, db, email: str, password: str) -> User:
        # Explicit duplicate check
        if self.user_repo.get_by_email(db, email):
            raise AuthError("Email already exists")
        hashed = self.hash_password(password)
        try:
            user = self.user_repo.create(db, email, hashed)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to create user")
        self.features_service.create_default_settings(db, user.id)
        self.caching_service.delete(f"auth:user:email:{email}")
        return user

    def authenticate_user(self, db, email: str, password: str):
        cache_key = f"auth:user:email:{email}"
        user = None
        try:
            cached_user = self.caching_service.get(cache_key)
            if cached_user:
                user = User.from_dict(cached_user)
        except (pickle.PickleError, TypeError) as e:
            logging.warning(f"Cache retrieval failed for key {cache_key}: {str(e)}")

        if not user:
            try:
                user = self.user_repo.get_by_email(db, email)
            except Exception as e:
                raise wrap_external_error(e, DatabaseError, "Failed to retrieve user")
            if user:
                self.caching_service.set(
                    cache_key,
                    user.__dict__,
                    timeout=300
                )

        if user:
            if user.failed_logins >= self.failed_login_threshold:
                self.log_anomaly("login_failed", {"email": email})
                raise AuthError("Account locked due to too many failed attempts")
            if self.verify_password(password, user.hashed_password):
                self.user_repo.update_failed_logins(db, user.id, 0)
                return user
            else:
                new_count = user.failed_logins + 1
                self.user_repo.update_failed_logins(db, user.id, new_count)
                self.log_anomaly("login_failed", {"email": email})
                return None
        self.log_anomaly("login_failed", {"email": email})
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def _fetch_apple_jwks(self):
        try:
            with requests.Session() as session:
                return session.get(self.apple_jwks_url).json()
        except requests.RequestException as e:
            logging.error(f"Failed to fetch Apple JWKS: {str(e)}")
            raise wrap_external_error(e, AuthError, "Failed to fetch Apple JWKS")

    def authenticate_apple_user(self, db, id_token: str, jwks: dict = None):
        try:
            if jwks is None:
                jwks = self._fetch_apple_jwks()
            header = jwt.get_unverified_header(id_token)
            key = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
            decoded = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                issuer="https://appleid.apple.com",
                audience=Config.APPLE_CLIENT_ID
            )
            email = decoded["email"]
            try:
                user = self.user_repo.get_by_email(db, email)
            except Exception as e:
                raise wrap_external_error(e, DatabaseError, "Failed to retrieve user")
            if not user:
                try:
                    user = self.user_repo.create(db, email, "")
                    user.is_verified = True
                    user.updated_at = TimeZone.utc_now()
                    db.commit()
                    self.features_service.create_default_settings(db, user.id)
                    self.caching_service.delete(f"auth:user:email:{email}")
                except Exception as e:
                    raise wrap_external_error(e, DatabaseError, "Failed to create Apple user")
            return user
        except (jwt.InvalidTokenError, ValueError, TypeError) as e:
            self.log_anomaly("apple_auth_failed", {"error": str(e)})
            raise wrap_external_error(e, AuthError, "Apple JWT verification failed")

    @staticmethod
    def log_anomaly(event_type: str, details: dict):
        extra = {"event_type": event_type, "details": details, "timestamp": TimeZone.utc_now().isoformat()}
        logging.error("ANOMALY", extra=extra)

    def request_password_reset(self, db: Session, email: str):
        user = self.user_repo.get_by_email(db, email)
        if not user:
            raise AuthError("User not found")
        if not user.is_verified:
            raise AuthError("Account not verified")

        token = secrets.token_urlsafe(32)
        expires = TimeZone.utc_now() + timedelta(hours=1)
        self.user_repo.create_reset_token(db, user.id, token, expires)

        reset_url = f"{current_app.config.get('FRONTEND_BASE_URL', 'http://localhost:3000')}/reset-password?token={token}"
        self._send_email(email, "Password Reset Request", f"Click to reset your password: {reset_url}")

    def reset_password(self, db: Session, token: str, new_password: str):
        rt = self.user_repo.validate_reset_token(db, token)
        if not rt:
            raise AuthError("Invalid or expired reset token")

        hashed = self.hash_password(new_password)
        user = self.user_repo.update_password(db, rt.user_id, hashed)
        if not user:
            raise DatabaseError("User not found for password update")

        self.user_repo.delete_reset_token(db, token)
        self.user_repo.update_failed_logins(db, user.id, 0)
        self.caching_service.delete(f"auth:user:email:{user.email}")

        return user


    # NEW: General _send_email method (moved from EmailVerificationService for reuse)
    def _send_email(self, to_email: str, subject: str, body: str):
        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=body,
            html=f"<p>{body}</p>",  # Simple HTML version
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        try:
            current_app.extensions['mail'].send(msg)
            logging.info(f"Email sent to {to_email}: {subject}")
        except smtplib.SMTPAuthenticationError as e:
            logging.error(f"SMTP authentication failed for {to_email}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "SMTP authentication failed")
        except smtplib.SMTPRecipientsRefused as e:
            logging.error(f"SMTP recipients refused for {to_email}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Invalid recipient email")
        except smtplib.SMTPServerDisconnected as e:
            logging.error(f"SMTP server disconnected for {to_email}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "SMTP server connection lost")
        except smtplib.SMTPDataError as e:
            logging.error(f"SMTP data error for {to_email}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to send email data")
        except smtplib.SMTPException as e:
            logging.error(f"General SMTP error for {to_email}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to send email")
        except Exception as e:
            logging.error(f"Unexpected error sending email to {to_email}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Email sending failed")


# --- Token issuance / verification (cookie-based auth) ---

    @staticmethod
    def issue_access_token(user_id: int) -> str:
        return jwt.encode(
            {
                "sub": str(user_id),
                "type": "access",
                "exp": TimeZone.utc_now() + timedelta(hours=current_app.config["JWT_EXP_HOURS"]),
            },
            current_app.config["JWT_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"],
        )

    @staticmethod
    def issue_refresh_token(user_id: int) -> str:
        return jwt.encode(
            {
                "sub": str(user_id),
                "type": "refresh",
                "exp": TimeZone.utc_now() + timedelta(days=current_app.config["JWT_REFRESH_EXP_DAYS"]),
            },
            current_app.config["JWT_REFRESH_SECRET_KEY"],
            algorithm=current_app.config["JWT_ALGORITHM"],
        )

    def issue_token_pair(self, user_id: int) -> dict:
        return {
            "access_token": self.issue_access_token(user_id),
            "refresh_token": self.issue_refresh_token(user_id),
        }

    def verify_refresh_token(self, db: Session, token: str) -> User:
        try:
            payload = jwt.decode(
                token,
                current_app.config["JWT_REFRESH_SECRET_KEY"],
                algorithms=[current_app.config["JWT_ALGORITHM"]],
            )
        except jwt.ExpiredSignatureError as e:
            raise wrap_external_error(e, AuthError, "Refresh token expired")
        except jwt.InvalidTokenError as e:
            raise wrap_external_error(e, AuthError, "Invalid refresh token")

        if payload.get("type") != "refresh":
            raise AuthError("Invalid token type for refresh")

        sub = payload.get("sub")
        if not sub:
            raise AuthError("Malformed refresh token")

        user = self.user_repo.get_by_id(db, int(sub))
        if not user:
            raise AuthError("User not found")
        return user