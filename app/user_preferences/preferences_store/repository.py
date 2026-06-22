# app/user_preferences/preferences_store/repository.py
from typing import Optional, Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.base import AbstractRepository
from app.user_preferences.models.entities import UserPreferences
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone


def _handle_integrity_errors(e):
    if isinstance(e, IntegrityError):
        error_str = str(e.orig) if hasattr(e, "orig") else str(e)

        if "check_block_size_positive" in error_str:
            raise DatabaseError("Block size must be positive")
        if "check_max_blocks_positive" in error_str:
            raise DatabaseError("Max blocks per day must be positive")
        if "check_work_hours_positive" in error_str:
            raise DatabaseError("Work hours must be positive")

        raise DatabaseError(f"Integrity error: {error_str}")

    raise wrap_external_error(e, DatabaseError, "Failed to save preferences")


class PreferencesRepository(AbstractRepository):

    def create_or_update(self, db: Session, preferences: UserPreferences) -> UserPreferences | None | Any:
        try:
            existing = db.query(UserPreferences).filter_by(
                user_id=preferences.user_id
            ).first()

            target = existing or preferences

            if existing:
                existing.block_size_minutes = preferences.block_size_minutes
                existing.max_blocks_per_day = preferences.max_blocks_per_day
                existing.work_hours = preferences.work_hours
                existing.allow_weekends = preferences.allow_weekends
                existing.time_zone = preferences.time_zone
                existing.updated_at = TimeZone.utc_now()
            else:
                db.add(preferences)

            db.commit()
            db.refresh(target)
            return target

        except Exception as e:
            db.rollback()
            _handle_integrity_errors(e)


    def get_by_user(self, db: Session, user_id: int) -> Optional[UserPreferences]:
        try:
            return (
                db.query(UserPreferences)
                .filter(UserPreferences.user_id == user_id)
                .first()
            )
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve preferences")


    def delete_by_user(self, db: Session, user_id: int) -> None:
        try:
            db.query(UserPreferences).filter_by(user_id=user_id).delete()
            db.commit()
        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to delete preferences")