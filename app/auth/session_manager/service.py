# app/auth/session_manager/service.py
import base64
import logging
import pickle
import secrets
import smtplib
from datetime import timedelta
from io import BytesIO
from typing import Optional, Dict, Any, List

import jwt
import pyotp
import qrcode
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
        # === NEW: Add Apple token URL ===
        self.apple_token_url = "https://appleid.apple.com/auth/token"
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
        except Exception:
            return False

    def create_user(self, db: Session, email: str, password: str) -> User:
        existing_user = self.user_repo.get_by_email(db, email)
        if existing_user:
            raise AuthError("Email already exists")

        hashed_password = self.hash_password(password)
        try:
            user = self.user_repo.create(db, email, hashed_password)
            self.features_service.create_default_settings(db, user.id)
            return user
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to create user")

    def authenticate_user(self, db: Session, email: str, password: str) -> Optional[User]:
        try:
            cache_key = f"auth:user:email:{email}"
            cached_user = self.caching_service.get(cache_key)

            if cached_user:
                user = User.from_dict(cached_user)
            else:
                user = self.user_repo.get_by_email(db, email)
                if user:
                    self.caching_service.set(cache_key, user.__dict__, timeout=300)

            if user:
                if user.failed_logins >= self.failed_login_threshold:
                    self.log_anomaly("excessive_failed_logins", {"email": email})
                    raise AuthError("Account temporarily locked due to multiple failed login attempts")

                if self.verify_password(password, user.hashed_password):
                    if user.failed_logins > 0:
                        self.user_repo.update_failed_logins(db, user.id, 0)
                        self.caching_service.delete(cache_key)
                    return user
                else:
                    new_count = user.failed_logins + 1
                    self.user_repo.update_failed_logins(db, user.id, new_count)
                    self.log_anomaly("login_failed", {"email": email})
                    return None

            self.log_anomaly("login_failed", {"email": email})
            return None

        except AuthError:
            raise
        except Exception as e:
            logging.error(f"Authentication error: {str(e)}")
            raise wrap_external_error(e, DatabaseError, "Authentication failed")

    # === NEW: Apple Sign-In Methods ===
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def _fetch_apple_jwks(self):
        try:
            with requests.Session() as session:
                response = session.get(self.apple_jwks_url)
                response.raise_for_status()
                return response.json()
        except requests.RequestException as e:
            logging.error(f"Failed to fetch Apple JWKS: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to fetch Apple JWKS")

    def authenticate_apple_user(self, db: Session, id_token: str, jwks: dict = None, user_info: dict = None) -> User:
        """Authenticate user with Apple ID token"""
        try:
            if jwks is None:
                jwks = self._fetch_apple_jwks()

            # Decode and verify the ID token
            header = jwt.get_unverified_header(id_token)
            key = next((k for k in jwks["keys"] if k["kid"] == header["kid"]), None)

            if not key:
                raise AuthError("Invalid Apple ID token - key not found")

            # Verify the token
            decoded = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                issuer="https://appleid.apple.com",
                audience=Config.APPLE_CLIENT_ID,
                options={"verify_exp": True}
            )

            email = decoded.get("email")
            if not email:
                raise AuthError("Email not provided in Apple ID token")

            # Check if user exists
            try:
                user = self.user_repo.get_by_email(db, email)
            except Exception as e:
                raise wrap_external_error(e, DatabaseError, "Failed to retrieve user")

            # Create new user if doesn't exist
            if not user:
                try:
                    # Generate a secure random password for Apple users
                    random_password = secrets.token_urlsafe(32)
                    hashed_password = self.hash_password(random_password)

                    user = self.user_repo.create(db, email, hashed_password)
                    user.is_verified = True  # Apple users are pre-verified

                    # Set user's name if provided
                    if user_info and user_info.get("name"):
                        name_info = user_info["name"]
                        # Note: You'd need to add first_name and last_name columns to User model
                        # if hasattr(user, 'first_name') and name_info.get("firstName"):
                        #     user.first_name = name_info["firstName"]
                        # if hasattr(user, 'last_name') and name_info.get("lastName"):
                        #     user.last_name = name_info["lastName"]

                    user.updated_at = TimeZone.utc_now()

                    # Create default settings
                    self.features_service.create_default_settings(db, user.id)

                    # Clear cache
                    self.caching_service.delete(f"auth:user:email:{email}")

                except Exception as e:
                    raise wrap_external_error(e, DatabaseError, "Failed to create Apple user")

            return user

        except jwt.InvalidTokenError as e:
            self.log_anomaly("apple_auth_failed", {"error": str(e)})
            raise wrap_external_error(e, AuthError, "Invalid Apple ID token")
        except (ValueError, TypeError, KeyError) as e:
            self.log_anomaly("apple_auth_failed", {"error": str(e)})
            raise wrap_external_error(e, AuthError, "Apple authentication failed")

    def exchange_apple_authorization_code(self, db: Session, authorization_code: str, user_info: dict = None) -> User:
        """Exchange Apple authorization code for tokens"""
        try:
            # Prepare token exchange request
            data = {
                "client_id": Config.APPLE_CLIENT_ID,
                "client_secret": self._generate_apple_client_secret(),
                "code": authorization_code,
                "grant_type": "authorization_code"
            }

            # Exchange code for tokens
            with requests.Session() as session:
                response = session.post(self.apple_token_url, data=data)
                response.raise_for_status()
                token_response = response.json()

            # Extract and verify ID token
            id_token = token_response.get("id_token")
            if not id_token:
                raise AuthError("No ID token received from Apple")

            # Authenticate with the ID token
            return self.authenticate_apple_user(db, id_token, user_info=user_info)

        except requests.RequestException as e:
            logging.error(f"Failed to exchange Apple authorization code: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to exchange authorization code")

    def _generate_apple_client_secret(self) -> str:
        """Generate client secret for Apple Sign In"""
        # This would typically use Apple's private key to generate a JWT
        # For production, implement proper client secret generation
        # See: https://developer.apple.com/documentation/sign_in_with_apple/generate_and_validate_tokens
        return Config.APPLE_CLIENT_SECRET if hasattr(Config, 'APPLE_CLIENT_SECRET') else ""

    # === END Apple Sign-In Methods ===

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

    # === NEW: 2FA Methods ===
    def generate_2fa_setup(self, db: Session, user_id: int) -> Dict[str, Any]:
        """Generate 2FA setup data including QR code"""
        user = self.user_repo.get_by_id(db, user_id)
        if not user:
            raise AuthError("User not found")

        # Generate or use existing secret
        if not user.two_factor_secret:
            secret = pyotp.random_base32()
            # Temporarily store the secret (not enabled yet)
            user.two_factor_secret = secret
        else:
            secret = user.two_factor_secret

        # Generate provisioning URI for QR code
        totp_uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=current_app.config.get('APP_NAME', 'SmartScheduler')
        )

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")

        qr_base64 = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

        return {
            "qr_code": qr_base64,
            "secret": secret,
            "manual_entry_key": secret,
            "issuer": current_app.config.get('APP_NAME', 'SmartScheduler')
        }

    def enable_2fa(self, db: Session, user_id: int, code: str, secret: str = None) -> Dict[str, Any]:
        """Enable 2FA after verifying the setup code"""
        user = self.user_repo.get_by_id(db, user_id)
        if not user:
            raise AuthError("User not found")

        # Use provided secret or existing one
        secret_to_verify = secret or user.two_factor_secret
        if not secret_to_verify:
            raise AuthError("No 2FA secret found")

        # Verify the code
        totp = pyotp.TOTP(secret_to_verify)
        if not totp.verify(code, valid_window=1):
            return None

        # Generate backup codes
        backup_codes = self.user_repo.generate_backup_codes()

        # Enable 2FA with hashed backup codes
        self.user_repo.enable_2fa(db, user_id, secret_to_verify, backup_codes)

        # Clear cache
        self.caching_service.delete(f"auth:user:id:{user_id}")
        self.caching_service.delete(f"auth:user:email:{user.email}")

        return {
            "success": True,
            "backup_codes": backup_codes  # Return unhashed codes to user once
        }

    def verify_2fa_code(self, db: Session, user_id: int, code: str) -> bool:
        """Verify a 2FA code or backup code"""
        user = self.user_repo.get_by_id(db, user_id)
        if not user or not user.two_factor_enabled:
            raise AuthError("2FA not enabled for this user")

        # First try TOTP verification
        totp = pyotp.TOTP(user.two_factor_secret)
        if totp.verify(code, valid_window=1):
            return True

        # Try backup codes if TOTP fails
        if user.backup_codes:
            for i, hashed_code in enumerate(user.backup_codes):
                if pwd_context.verify(code, hashed_code):
                    # Remove used backup code
                    user.backup_codes.pop(i)
                    user.updated_at = TimeZone.utc_now()
                    return True

        return False

    def disable_2fa(self, db: Session, user_id: int) -> bool:
        """Disable 2FA for a user"""
        user = self.user_repo.get_by_id(db, user_id)
        if not user:
            raise AuthError("User not found")

        user.two_factor_enabled = False
        user.two_factor_secret = None
        user.backup_codes = None
        user.updated_at = TimeZone.utc_now()

        # Clear cache
        self.caching_service.delete(f"auth:user:id:{user_id}")
        self.caching_service.delete(f"auth:user:email:{user.email}")

        return True

    def get_backup_codes_info(self, db: Session, user_id: int) -> Dict[str, Any]:
        """Get information about user's backup codes and 2FA status"""
        # Clear any cache first
        cache_key = f"auth:user:id:{user_id}"
        self.caching_service.delete(cache_key)

        # Force fresh read from database
        db.expire_all()

        user = self.user_repo.get_by_id(db, user_id)
        if not user:
            raise AuthError("User not found")

        # Log the actual database values
        logging.info(
            f"[get_backup_codes_info] User {user_id} - 2FA enabled: {user.two_factor_enabled}, backup_codes: {len(user.backup_codes) if user.backup_codes else 0}")

        result = {
            "codes_remaining": len(user.backup_codes) if user.backup_codes else 0,
            "two_factor_enabled": bool(user.two_factor_enabled)
        }

        logging.info(f"[get_backup_codes_info] Returning: {result}")

        return result

    def regenerate_backup_codes(self, db: Session, user_id: int) -> List[str]:
        """Regenerate backup codes for a user"""
        user = self.user_repo.get_by_id(db, user_id)
        if not user:
            raise AuthError("User not found")

        if not user.two_factor_enabled:
            raise AuthError("2FA not enabled")

        # Generate new backup codes
        backup_codes = self.user_repo.generate_backup_codes()

        # Store hashed versions
        user.backup_codes = [pwd_context.hash(code) for code in backup_codes]
        user.updated_at = TimeZone.utc_now()

        # Clear cache
        self.caching_service.delete(f"auth:user:id:{user_id}")

        return backup_codes  # Return unhashed codes to user

    # === END 2FA Methods ===

    def _send_email(self, to_email: str, subject: str, body: str):
        """Send email using Flask-Mail"""
        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=body,
            html=f"<p>{body}</p>",
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
        except Exception as e:
            logging.error(f"Failed to send email to {to_email}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to send email")