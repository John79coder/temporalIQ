from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from app.extensions import db
from app.analytics.models.entities import UserEvent, EventAggregate


class EventTracker:
    """
    Separate service for tracking user behavior and business events.
    This is distinct from application logging.
    """

    def __init__(self):
        self.batch_size = 100
        self.event_buffer = []

    def track(
            self,
            user_id: int,
            event_name: str,
            properties: Optional[Dict[str, Any]] = None,
            timestamp: Optional[datetime] = None
    ):
        """Track a user behavior event"""

        event = UserEvent(
            user_id=user_id,
            event_name=event_name,
            properties=properties or {},
            timestamp=timestamp or datetime.utcnow()
        )

        self.event_buffer.append(event)

        # Batch persist events
        if len(self.event_buffer) >= self.batch_size:
            self.flush()

    def track_task_scheduled(self, user_id: int, task_id: int, calendar_id: str):
        """Track task scheduling event"""
        self.track(
            user_id=user_id,
            event_name="task_scheduled",
            properties={
                "task_id": task_id,
                "calendar_id": calendar_id
            }
        )

    def track_notion_connected(self, user_id: int, database_count: int):
        """Track Notion connection event"""
        self.track(
            user_id=user_id,
            event_name="notion_connected",
            properties={
                "database_count": database_count
            }
        )

    def track_feature_usage(self, user_id: int, feature_name: str, metadata: dict = None):
        """Track feature usage"""
        self.track(
            user_id=user_id,
            event_name="feature_used",
            properties={
                "feature_name": feature_name,
                **(metadata or {})
            }
        )

    def track_sync_event(
            self,
            user_id: int,
            sync_type: str,
            success: bool,
            duration_ms: float,
            error_message: Optional[str] = None
    ):
        """Track synchronization events"""
        self.track(
            user_id=user_id,
            event_name=f"sync_{sync_type}",
            properties={
                "success": success,
                "duration_ms": duration_ms,
                "error_message": error_message
            }
        )

    def flush(self):
        """Persist buffered events to database"""
        if not self.event_buffer:
            return

        try:
            db.session.bulk_save_objects(self.event_buffer)
            db.session.commit()
            self.event_buffer = []
        except Exception as e:
            # Log error but don't fail the request
            from app.logging.services.application_logger import ApplicationLogger
            logger = ApplicationLogger()
            logger.error(f"Failed to persist events: {e}", exception=e)
            self.event_buffer = []  # Clear buffer to prevent memory issues

    def get_user_metrics(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get aggregated metrics for a user"""

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        events = db.session.query(UserEvent).filter(
            UserEvent.user_id == user_id,
            UserEvent.timestamp >= cutoff_date
        ).all()

        metrics = {
            "total_events": len(events),
            "unique_event_types": len(set(e.event_name for e in events)),
            "tasks_scheduled": sum(1 for e in events if e.event_name == "task_scheduled"),
            "sync_success_rate": self._calculate_sync_success_rate(events),
            "most_used_features": self._get_top_features(events),
            "activity_by_day": self._get_activity_by_day(events)
        }

        return metrics

    def _calculate_sync_success_rate(self, events: list) -> float:
        """Calculate sync success rate from events"""
        sync_events = [e for e in events if e.event_name.startswith("sync_")]
        if not sync_events:
            return 0.0

        successful = sum(1 for e in sync_events if e.properties.get("success", False))
        return (successful / len(sync_events)) * 100

    def _get_top_features(self, events: list, limit: int = 5) -> list:
        """Get most used features"""
        feature_counts = {}
        for event in events:
            if event.event_name == "feature_used":
                feature_name = event.properties.get("feature_name")
                if feature_name:
                    feature_counts[feature_name] = feature_counts.get(feature_name, 0) + 1

        return sorted(
            [{"feature": k, "count": v} for k, v in feature_counts.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:limit]

    def _get_activity_by_day(self, events: list) -> dict:
        """Get activity grouped by day"""
        activity = {}
        for event in events:
            day = event.timestamp.date().isoformat()
            activity[day] = activity.get(day, 0) + 1
        return activity