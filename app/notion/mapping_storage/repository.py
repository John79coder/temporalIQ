# app/notion/mapping_storage/repository.py
from sqlalchemy.orm import Session
from app.notion.models.entities import FieldMapping
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.repositories.base import AbstractRepository
from app.utils.time_zone import TimeZone

class MappingRepository(AbstractRepository):
    @staticmethod
    def save(db: Session, mapping: FieldMapping):
        with db.begin(nested=True):
            existing = db.query(FieldMapping).filter_by(user_id=mapping.user_id, notion_db_id=mapping.notion_db_id).first()
            if existing:
                existing.title_field = mapping.title_field
                existing.due_date_field = mapping.due_date_field
                existing.duration_field = mapping.duration_field
                existing.updated_at = TimeZone.utc_now()
                db.flush()
                db.refresh(existing)
                return existing
            db.add(mapping)
            db.flush()
            db.refresh(mapping)
            return mapping

    @staticmethod
    def get_mapping(db: Session, user_id: int, notion_db_id: str) -> FieldMapping | None:
        try:
            return db.query(FieldMapping).filter_by(user_id=user_id, notion_db_id=notion_db_id).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve mapping")