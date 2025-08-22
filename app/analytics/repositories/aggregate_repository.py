from typing import List, Optional, Dict, Any
from datetime import date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.analytics.models.entities import EventAggregate
from app.utils.exceptions import DatabaseError, wrap_external_error


class AggregateRepository:
    """Repository for event aggregate data access"""

    def upsert_aggregate(
            self,
            db: Session,
            user_id: int,
            date: date,
            event_name: str,
            aggregate_data: Dict[str, Any]
    ) -> EventAggregate:
        """Insert or update an aggregate record"""
        try:
            aggregate = db.query(EventAggregate).filter(
                EventAggregate.user_id == user_id,
                EventAggregate.date == date,
                EventAggregate.event_name == event_name
            ).first()

            if aggregate:
                # Update existing
                for key, value in aggregate_data.items():
                    setattr(aggregate, key, value)
            else:
                # Create new
                aggregate = EventAggregate(
                    user_id=user_id,
                    date=date,
                    event_name=event_name,
                    **aggregate_data
                )
                db.add(aggregate)

            db.commit()
            db.refresh(aggregate)
            return aggregate

        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to upsert aggregate")

    def get_user_aggregates(
            self,
            db: Session,
            user_id: int,
            start_date: date,
            end_date: date,
            event_names: Optional[List[str]] = None
    ) -> List[EventAggregate]:
        """Get aggregates for a user within date range"""
        try:
            query = db.query(EventAggregate).filter(
                EventAggregate.user_id == user_id,
                EventAggregate.date >= start_date,
                EventAggregate.date <= end_date
            )

            if event_names:
                query = query.filter(EventAggregate.event_name.in_(event_names))

            return query.order_by(EventAggregate.date).all()

        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to get user aggregates")

    def get_top_users_by_event(
            self,
            db: Session,
            event_name: str,
            date: date,
            limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top users by event count for a specific date"""
        try:
            results = db.query(
                EventAggregate.user_id,
                EventAggregate.count
            ).filter(
                EventAggregate.event_name == event_name,
                EventAggregate.date == date
            ).order_by(
                EventAggregate.count.desc()
            ).limit(limit).all()

            return [
                {"user_id": r[0], "count": r[1]}
                for r in results
            ]

        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to get top users")

    def get_event_trends(
            self,
            db: Session,
            event_name: str,
            start_date: date,
            end_date: date
    ) -> List[Dict[str, Any]]:
        """Get daily trends for an event"""
        try:
            results = db.query(
                EventAggregate.date,
                func.sum(EventAggregate.count).label('total_count'),
                func.count(func.distinct(EventAggregate.user_id)).label('unique_users')
            ).filter(
                EventAggregate.event_name == event_name,
                EventAggregate.date >= start_date,
                EventAggregate.date <= end_date
            ).group_by(
                EventAggregate.date
            ).order_by(
                EventAggregate.date
            ).all()

            return [
                {
                    "date": r[0].isoformat(),
                    "total_count": r[1],
                    "unique_users": r[2]
                }
                for r in results
            ]

        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to get event trends")

    def delete_old_aggregates(
            self,
            db: Session,
            days_to_keep: int = 365
    ) -> int:
        """Delete aggregates older than specified days"""
        try:
            cutoff_date = date.today() - timedelta(days=days_to_keep)

            deleted = db.query(EventAggregate).filter(
                EventAggregate.date < cutoff_date
            ).delete()

            db.commit()
            return deleted

        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to delete old aggregates")