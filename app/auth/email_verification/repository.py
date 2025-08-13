# app/auth/email_verification/repository.py
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.auth.models.entities import VerificationToken
from app.repositories.base import AbstractRepository
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone


class TokenRepository(AbstractRepository):
    def create(self, db: Session, user_id: int, token: str, expires_at: datetime) -> VerificationToken:
        with db.begin(nested=True):
            vt = VerificationToken(user_id=user_id, token=token, expires_at=expires_at)
            db.add(vt)
            return vt

    def validate_token(self, db: Session, token: str) -> VerificationToken | None:
        try:
            now = TimeZone.utc_now()
            return db.query(VerificationToken).filter(VerificationToken.token == token,
                                                      VerificationToken.expires_at > now).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to validate token")

    def delete_by_token(self, db: Session, token: str) -> None:
        with db.begin(nested=True):
            deleted = db.query(VerificationToken).filter(VerificationToken.token == token).delete()
            if deleted == 0:
                logging.warning(f"No token found to delete for token: {token}")
