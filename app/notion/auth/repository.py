# app/notion/auth/repository.py
from sqlalchemy.orm import Session

from app.utils.time_zone import TimeZone
from app.notion.models.entities import NotionConnection
from app.utils.exceptions import DatabaseError, wrap_external_error

class NotionAuthRepository:

    @staticmethod
    def save_connection(db: Session, connection: NotionConnection) -> None:
        with db.begin(nested=True):
            existing = db.query(NotionConnection).filter_by(user_id=connection.user_id).first()
            if existing:
                existing.access_token = connection.access_token
                existing.refresh_token = connection.refresh_token
                existing.expires_at = connection.expires_at
                existing.workspace_id = connection.workspace_id
                existing.updated_at = TimeZone.utc_now()
            else:
                db.add(connection)

    @staticmethod
    def get_connection(db: Session, user_id: int) -> NotionConnection | None:
        try:
            return db.query(NotionConnection).filter_by(user_id=user_id).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve Notion connection")