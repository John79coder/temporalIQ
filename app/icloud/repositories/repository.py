# app/icloud/repositories/repository.py
from sqlalchemy.orm import Session

from app.icloud.models.entities import iCloudConnection, CalendarSelection
from app.repositories.base import AbstractRepository
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone


class ICloudRepository(AbstractRepository):
    @staticmethod
    def save_icloud_connection(db: Session, connection: iCloudConnection) -> None:
        with db.begin(nested=True):
            existing = db.query(iCloudConnection).filter(iCloudConnection.user_id == connection.user_id).first()
            if existing:
                existing.encrypted_app_password = connection.encrypted_app_password
                existing.updated_at = TimeZone.utc_now()
            else:
                db.add(connection)

    @staticmethod
    def update_icloud_connection(db: Session, user_id: int, encrypted_app_password: str) -> iCloudConnection | None:
        with db.begin(nested=True):
            connection = db.query(iCloudConnection).filter(iCloudConnection.user_id == user_id).first()
            if connection:
                connection.encrypted_app_password = encrypted_app_password
                connection.updated_at = TimeZone.utc_now()
                db.flush()
                db.refresh(connection)
            return connection

    @staticmethod
    def get_icloud_connection_by_user(db: Session, user_id: int) -> iCloudConnection | None:
        try:
            return db.query(iCloudConnection).filter(iCloudConnection.user_id == user_id).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve iCloud connection")

    @staticmethod
    def save_calendar_selection(db: Session, selection: CalendarSelection) -> None:
        with db.begin(nested=True):
            if selection.is_default:
                db.query(CalendarSelection).filter(
                    CalendarSelection.user_id == selection.user_id,
                    CalendarSelection.is_default == True
                ).update({"is_default": False})
            db.add(selection)

    @staticmethod
    def get_default_calendar_for_user(db: Session, user_id: int) -> CalendarSelection | None:
        try:
            return db.query(CalendarSelection).filter(
                CalendarSelection.user_id == user_id,
                CalendarSelection.is_default == True
            ).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve default calendar")
