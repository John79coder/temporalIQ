# app/notion/repositories/repository.py
from typing import List

from flask import current_app
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.notion.models.entities import NotionConnection, FieldMapping, TaskCandidate
from app.repositories.base import AbstractRepository
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone


class NotionAuthRepository(AbstractRepository):
    @staticmethod
    def save_connection(db: Session, connection: NotionConnection) -> None:

        current_app.logger.info(
            "Saving Notion connection for user_id=%s",
            connection.user_id,
        )

        with db.begin(nested=True):
            existing = (
                db.query(NotionConnection)
                .filter_by(user_id=connection.user_id)
                .first()
            )

            current_app.logger.info(
                "Existing connection found: %s",
                existing is not None,
            )

            if existing:
                existing.access_token = connection.access_token
                existing.refresh_token = connection.refresh_token
                existing.expires_at = connection.expires_at
                existing.workspace_id = connection.workspace_id
                existing.updated_at = TimeZone.utc_now()
            else:
                db.add(connection)

            db.flush()

            current_app.logger.info(
                "After flush: id=%s created_at=%s",
                connection.id,
                connection.created_at,
            )

    @staticmethod
    def get_connection(db: Session, user_id: int) -> NotionConnection | None:
        try:
            return db.query(NotionConnection).filter_by(user_id=user_id).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve Notion connection")


class MappingRepository(AbstractRepository):
    @staticmethod
    def save_mapping(db: Session, mapping: FieldMapping) -> FieldMapping:
        try:
            existing = db.query(FieldMapping).filter_by(user_id=mapping.user_id,
                                                        notion_db_id=mapping.notion_db_id).first()
            if existing:
                existing.title_field = mapping.title_field
                existing.due_date_field = mapping.due_date_field
                existing.duration_field = mapping.duration_field
                existing.updated_at = TimeZone.utc_now()
                db.commit()
                db.refresh(existing)
                return existing
            db.add(mapping)
            db.commit()
            db.refresh(mapping)
            return mapping
        except IntegrityError:
            db.rollback()
            raise DatabaseError("Failed to save mapping: duplicate user/database combination")
        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to save mapping")

    @staticmethod
    def get_mapping(db: Session, user_id: int, notion_db_id: str) -> FieldMapping | None:
        try:
            return db.query(FieldMapping).filter_by(user_id=user_id, notion_db_id=notion_db_id).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve mapping")


class TaskCandidateRepository(AbstractRepository):
    @staticmethod
    def save_candidates(db: Session, candidates: List[TaskCandidate]) -> None:
        with db.begin(nested=True):
            db.add_all(candidates)

    @staticmethod
    def get_candidates(db: Session, user_id: int, notion_db_id: str) -> List[TaskCandidate]:
        try:
            return db.query(TaskCandidate).filter_by(user_id=user_id, notion_db_id=notion_db_id).all()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve task candidates")
