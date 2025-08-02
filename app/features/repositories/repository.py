# app/features/repositories/repository.py
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.features.models.entities import UserAISettings, AITrainingEvent
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.repositories.base import AbstractRepository
from app.utils.time_zone import TimeZone
from app.utils.logging_service import LoggingService

class FeaturesRepository(AbstractRepository):
    def __init__(self, logging_service: LoggingService):
        self.logging_service = logging_service

    def create(self, db: Session, settings: UserAISettings) -> UserAISettings:
        """Create new AI settings for a user."""

        try:
            db.add(settings)
            db.commit()
            db.refresh(settings)
            return settings
        except SQLAlchemyError as e:
            db.rollback()
            self.logging_service.error("Failed to create AI settings", user_id=settings.user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to create AI settings") from e

    def update(self, db: Session, settings: UserAISettings) -> UserAISettings:
        """Update existing AI settings for a user."""
        try:
            existing = db.query(UserAISettings).filter_by(user_id=settings.user_id).first()
            if not existing:
                raise DatabaseError("Settings not found")
            existing.use_llm_mapping = settings.use_llm_mapping
            existing.use_learned_detector = settings.use_learned_detector
            existing.use_spacy_heuristics = settings.use_spacy_heuristics
            existing.use_embedding_similarity = settings.use_embedding_similarity
            existing.use_ml_prioritization = settings.use_ml_prioritization
            existing.use_nlp_urgency = settings.use_nlp_urgency
            existing.use_rl_optimization = settings.use_rl_optimization
            existing.urgency_learning_scope = settings.urgency_learning_scope
            existing.duration_learning_scope = settings.duration_learning_scope
            existing.mapping_learning_scope = settings.mapping_learning_scope
            existing.slot_ranking_learning_scope = settings.slot_ranking_learning_scope
            existing.use_nlp_scoring = settings.use_nlp_scoring
            existing.updated_at = TimeZone.utc_now()
            db.commit()
            db.refresh(existing)
            return existing
        except SQLAlchemyError as e:
            db.rollback()
            self.logging_service.error("Failed to update AI settings", user_id=settings.user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to update AI settings") from e

    def create_or_update(self, db: Session, settings: UserAISettings) -> UserAISettings:
        """Create or update AI settings for a user."""
        existing = db.query(UserAISettings).filter_by(user_id=settings.user_id).first()
        return self.update(db, settings) if existing else self.create(db, settings)

    def get_by_user(self, db: Session, user_id: int) -> Optional[UserAISettings]:
        """Retrieve AI settings by user ID."""
        try:
            return db.query(UserAISettings).filter_by(user_id=user_id).first()
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to retrieve AI settings", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve AI settings") from e

class AIDataRepository(AbstractRepository):
    def __init__(self, logging_service: LoggingService):
        self.logging_service = logging_service

    def log_event(self, db: Session, event: AITrainingEvent) -> None:
        """Log an AI training event."""
        try:
            with db.begin(nested=True):
                db.add(event)
        except SQLAlchemyError as e:
            db.rollback()
            self.logging_service.error("Failed to log AI training event", user_id=event.user_id, task_id=event.task_id, extra={"error": str(e), "event_type": event.event_type})
            raise wrap_external_error(e, DatabaseError, "Failed to log AI training event") from e

    def get_events_by_type(self, db: Session, event_type: str, user_id: Optional[int] = None) -> List[AITrainingEvent]:
        """Retrieve AI training events by type and optional user ID."""
        try:
            query = db.query(AITrainingEvent).filter_by(event_type=event_type)
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            return query.all()
        except SQLAlchemyError as e:
            self.logging_service.error(f"Failed to retrieve AI training events for type {event_type}", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, f"Failed to retrieve AI training events for type {event_type}") from e