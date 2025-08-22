from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session
from app.analytics.models.entities import UserEvent, EventAggregate
from app.utils.exceptions import DatabaseError, wrap_external_error


class EventRepository:
    """Repository for user event data access"""

    def create_event(self, db: Session, event_data: Dict[str, Any]) -> UserEvent:
        """Create a new user event"""
        try:
            event = UserEvent(**event_data)
            db.add(event)
            db.commit()
            db.refresh(event)
            return event
        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to create event")

    def bulk_create_events(self, db: Session, events: List[UserEvent]) -> int:
        """Bulk create multiple events"""
        try:
            db.bulk_save_objects(events)
            db.commit()
            return len(events)
        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to bulk create events")

    def get_user_events(
            self,
            db: Session,
            user_id: int,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None,
            event_names: Optional[List[str]] = None,
            limit: int = 1000
    ) -> List[UserEvent]:
        """Get events for a specific user"""
        try:
            query = db.query(UserEvent).filter(UserEvent.user_id == user_id)

            if start_date:
                query = query.filter(UserEvent.timestamp >= start_date)

            if end_date:
                query = query.filter(UserEvent.timestamp <= end_date)

            if event_names:
                query = query.filter(UserEvent.event_name.in_(event_names))

            return query.order_by(UserEvent.timestamp.desc()).limit(limit).all()

        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to get user events")

    def get_events_by_session(
            self,
            db: Session,
            session_id: str
    ) -> List[UserEvent]:
        """Get all events for a specific session"""
        try:
            return db.query(UserEvent).filter(
                UserEvent.session_id == session_id
            ).order_by(UserEvent.timestamp).all()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to get session events")

    def count_events(
            self,
            db: Session,
            user_id: Optional[int] = None,
            event_name: Optional[str] = None,
            start_date: Optional[datetime] = None,
            end_date: Optional[datetime] = None
    ) -> int:
        """Count events matching criteria"""
        try:
            query = db.query(func.count(UserEvent.id))
            conditions = []
            if user_id is not None:
                conditions.append(UserEvent.user_id == user_id)
            if event_name:
                conditions.append(UserEvent.event_name == event_name)
            if start_date is not None:
                conditions.append(UserEvent.timestamp >= start_date)
            if end_date is not None:
                conditions.append(UserEvent.timestamp <= end_date)
            if conditions:
                query = query.filter(*conditions)
            return query.scalar()


        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to count events")

    def get_unique_users(
            self,
            db: Session,
            event_name: str,
            start_date: datetime,
            end_date: datetime
    ) -> int:
        """Get count of unique users who performed an event"""
        try:
            return db.query(func.count(func.distinct(UserEvent.user_id))).filter(
                UserEvent.event_name == event_name,
                UserEvent.timestamp >= start_date,
                UserEvent.timestamp <= end_date
            ).scalar()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to count unique users")

    def delete_old_events(
            self,
            db: Session,
            days_to_keep: int = 90
    ) -> int:
        """Delete events older than specified days"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

            deleted = db.query(UserEvent).filter(
                UserEvent.timestamp < cutoff_date
            ).delete()

            db.commit()
            return deleted

        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to delete old events")