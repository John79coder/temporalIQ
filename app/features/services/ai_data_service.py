# app/features/services/ai_data_services.py
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.features.repositories.repository import AIDataRepository
from app.features.models.entities import AITrainingEvent
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.logging_service import LoggingService

class AIDataService:
    def __init__(self, repository: AIDataRepository, logging_service: LoggingService):
        self.repository = repository
        self.logging_service = logging_service

    def log_event(self, db: Session, event: AITrainingEvent) -> None:
        """Log an AI training event."""
        try:
            self.repository.log_event(db, event)
        except SQLAlchemyError as e:
            self.logging_service.error(
                "Failed to log AI training event",
                user_id=event.user_id,
                task_id=event.task_id,
                extra={"error": str(e), "event_type": event.event_type}
            )
            raise wrap_external_error(e, DatabaseError, "Failed to log AI training event") from e

    def get_events_by_type(self, db: Session, event_type: str, user_id: Optional[int] = None) -> List[AITrainingEvent]:
        """Retrieve AI training events by type and optional user ID."""
        try:
            return self.repository.get_events_by_type(db, event_type, user_id)
        except SQLAlchemyError as e:
            self.logging_service.error(
                f"Failed to retrieve AI training events for type {event_type}",
                user_id=user_id,
                extra={"error": str(e)}
            )
            raise wrap_external_error(e, DatabaseError, f"Failed to retrieve AI training events for type {event_type}") from e