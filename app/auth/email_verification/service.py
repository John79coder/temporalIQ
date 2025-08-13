# app/auth/email_verification/service.py
import logging
import secrets
import smtplib
from datetime import timedelta

from flask import current_app
from flask_mail import Message
from pydantic import EmailStr, ValidationError, TypeAdapter

from app.auth.email_verification.repository import TokenRepository
from app.extensions import mail
from app.utils.caching import ICacheService
from app.utils.exceptions import DataValidationError
from app.utils.exceptions import ServiceUnavailableError, DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone


class EmailVerificationService:
    def __init__(self, token_repo: TokenRepository, caching_service: ICacheService):
        self.token_repo = token_repo
        self.caching_service = caching_service

    def create_email_verification_token(self, db, user_id: int, email: str):
        try:
            TypeAdapter(EmailStr).validate_python(email)
        except ValidationError:
            raise DataValidationError("Invalid email address")
        token = secrets.token_urlsafe(32)
        expires = TimeZone.utc_now() + timedelta(hours=24)
        try:
            vt = self.token_repo.create(db, user_id, token, expires)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to create verification token")
        self._send_verification_email(email, token)
        return vt

    def verify_token(self, db, token: str):
        cache_key = f"auth:verification_token:{token}"
        cached_vt = self.caching_service.get(cache_key)
        if cached_vt:
            return cached_vt
        try:
            vt = self.token_repo.validate_token(db, token)
        except DatabaseError as e:
            raise e
        except ServiceUnavailableError as e:
            raise wrap_external_error(e, ServiceUnavailableError, "Email service unavailable")
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to validate token")
        if vt:
            self.caching_service.set(
                cache_key,
                vt.__dict__,
                timeout=300  # 5 minutes
            )
            # Delete token after successful verification
            self.token_repo.delete_by_token(db, token)
        return vt

    @staticmethod
    def _send_verification_email(to_email: str, token: str):
        verify_url = f"{current_app.config.get('FRONTEND_BASE_URL', 'http://localhost:3000')}/verify-email?token={token}"
        msg = Message(
            subject="Verify your email",
            recipients=[to_email],
            body=f"Click this link to verify your email: {verify_url}",
            html=f"<p>Click <a href='{verify_url}'>here</a> to verify your email.</p>"
        )
        try:
            mail.send(msg)
        except smtplib.SMTPAuthenticationError as e:
            logging.error(f"SMTP authentication failed: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "SMTP authentication failed")
        except smtplib.SMTPRecipientsRefused as e:
            logging.error(f"SMTP recipients refused: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Invalid recipient email")
        except smtplib.SMTPServerDisconnected as e:
            logging.error(f"SMTP server disconnected: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "SMTP server connection lost")
        except smtplib.SMTPException as e:
            logging.error(f"SMTP error: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to send verification email")
        finally:
            if hasattr(mail, 'connection') and mail.connection:
                mail.connection.close()
