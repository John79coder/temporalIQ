# app/auth/session_manager/repository.py
import logging
import secrets
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from app.auth.models.entities import User, PasswordResetToken
from app.repositories.base import AbstractRepository
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.security import pwd_context
from app.utils.time_zone import TimeZone


class UserRepository(AbstractRepository):

    @staticmethod
    def create(db: Session, email: str, hashed_password: str) -> User:
        with db.begin(nested=True):
            user = User(email=email, hashed_password=hashed_password, failed_logins=0)
            db.add(user)
            db.flush()
            db.refresh(user)
            return user

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        try:
            return db.query(User).filter(User.email == email).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve user by email")

    # NEW: Add get_by_id for user lookup by ID
    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[User]:
        try:
            return db.query(User).filter(User.id == user_id).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve user by ID")

    @staticmethod
    def update_verified(db: Session, user_id: int) -> Optional[User]:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_verified = True
            user.updated_at = TimeZone.utc_now()
            db.flush()
            db.refresh(user)
        return user

    @staticmethod
    def update_failed_logins(db: Session, user_id: int, count: int) -> None:
        with db.begin(nested=True):
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.failed_logins = count
                user.updated_at = TimeZone.utc_now()
                db.flush()
            else:
                raise DatabaseError("User not found for updating failed logins")

    @staticmethod
    def create_reset_token(db: Session, user_id: int, token: str, expires_at: datetime) -> PasswordResetToken:
        with db.begin(nested=True):
            rt = PasswordResetToken(user_id=user_id, token=token, expires_at=expires_at)
            db.add(rt)
            db.flush()
            db.refresh(rt)
            return rt

    @staticmethod
    def validate_reset_token(db: Session, token: str) -> Optional[PasswordResetToken]:
        try:
            now = TimeZone.utc_now()
            return db.query(PasswordResetToken).filter(
                PasswordResetToken.token == token,
                PasswordResetToken.expires_at > now
            ).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to validate reset token")

    @staticmethod
    def delete_reset_token(db: Session, token: str) -> None:
        with db.begin(nested=True):
            deleted = db.query(PasswordResetToken).filter(PasswordResetToken.token == token).delete()
            if deleted == 0:
                logging.warning(f"No reset token found to delete for token: {token}")

    @staticmethod
    def update_password(db: Session, user_id: int, hashed_password: str) -> Optional[User]:
        with db.begin(nested=True):
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.hashed_password = hashed_password
                user.updated_at = TimeZone.utc_now()
                db.flush()
                db.refresh(user)
            return user
