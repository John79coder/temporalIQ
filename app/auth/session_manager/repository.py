# app/auth/session_manager/repository.py
from typing import Optional
from sqlalchemy.orm import Session

from app.auth.models.entities import User
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.repositories.base import AbstractRepository
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

    @staticmethod
    def update_verified(db: Session, user_id: int) -> Optional[User]:
        with db.begin(nested=True):
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