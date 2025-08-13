# app/notion/mapping_storage/feedback.py
from typing import List, Optional

from sqlalchemy.orm import Session

from app.extensions import db
from app.repositories.base import AbstractRepository
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now, onupdate=TimeZone.utc_now)


class FeedbackLog(db.Model, TimestampMixin):
    __tablename__ = "notion_feedback_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    notion_db_id = db.Column(db.String, nullable=False)
    notion_field = db.Column(db.String, nullable=False)
    corrected_concept = db.Column(db.String, nullable=False)
    feedback_text = db.Column(db.String, nullable=True)


class FeedbackRepository(AbstractRepository):
    @staticmethod
    def save_feedback(db: Session, log: FeedbackLog) -> None:
        if db is None:
            return
        with db.begin(nested=True):
            db.add(log)

    @staticmethod
    def get_all_feedback(db: Optional[Session] = None, limit: Optional[int] = None, offset: int = 0) -> List[
        FeedbackLog]:
        if db is None:
            return []
        try:
            query = db.query(FeedbackLog)
            if limit is not None:
                query = query.offset(offset).limit(limit)
            return query.all()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve feedback logs")


class FeedbackService:
    def __init__(self, repo: FeedbackRepository):
        self.repo = repo

    def log_feedback(self, db: Optional[Session], user_id: int, notion_db_id: str, notion_field: str,
                     corrected_concept: str, feedback_text: Optional[str] = None) -> None:
        if db is None:
            return
        log = FeedbackLog(
            user_id=user_id,
            notion_db_id=notion_db_id,
            notion_field=notion_field,
            corrected_concept=corrected_concept,
            feedback_text=feedback_text
        )
        self.repo.save_feedback(db, log)
