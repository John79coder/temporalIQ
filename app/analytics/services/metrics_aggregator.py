from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import func
from app.extensions import db
from app.analytics.models.entities import UserEvent, EventAggregate
from app.analytics.repositories.aggregate_repository import AggregateRepository
from app.logging.services.application_logger import ApplicationLogger


class MetricsAggregator:
    """
    Service for aggregating raw events into metrics
    """

    def __init__(self):
        self.logger = ApplicationLogger()
        self.aggregate_repo = AggregateRepository()

    def run_aggregation(self, date: datetime = None):
        """
        Run aggregation for a specific date or yesterday
        """
        if date is None:
            date = datetime.utcnow().date() - timedelta(days=1)

        self.logger.info(f"Starting metrics aggregation for {date}")

        try:
            # Get all events for the date
            events = self._get_events_for_date(date)

            # Group by user and event type
            aggregates = self._compute_aggregates(events)

            # Save aggregates
            self._save_aggregates(aggregates, date)

            self.logger.info(
                f"Metrics aggregation completed",
                date=str(date),
                event_count=len(events),
                aggregate_count=len(aggregates)
            )

        except Exception as e:
            self.logger.error(
                f"Metrics aggregation failed",
                exception=e,
                date=str(date)
            )
            raise

    def _get_events_for_date(self, date: datetime.date) -> List[UserEvent]:
        """Get all events for a specific date"""
        start = datetime.combine(date, datetime.min.time())
        end = datetime.combine(date, datetime.max.time())

        return db.session.query(UserEvent).filter(
            UserEvent.timestamp >= start,
            UserEvent.timestamp <= end
        ).all()

    def _compute_aggregates(self, events: List[UserEvent]) -> List[Dict[str, Any]]:
        """Compute aggregates from events"""
        aggregates = {}

        for event in events:
            key = (event.user_id, event.event_name)

            if key not in aggregates:
                aggregates[key] = {
                    'user_id': event.user_id,
                    'event_name': event.event_name,
                    'count': 0,
                    'values': []
                }

            aggregates[key]['count'] += 1

            # Extract numeric values if present
            if event.properties and 'value' in event.properties:
                aggregates[key]['values'].append(event.properties['value'])

        # Compute statistics for numeric values
        result = []
        for key, data in aggregates.items():
            aggregate = {
                'user_id': data['user_id'],
                'event_name': data['event_name'],
                'count': data['count']
            }

            if data['values']:
                aggregate['sum_value'] = sum(data['values'])
                aggregate['avg_value'] = aggregate['sum_value'] / len(data['values'])
                aggregate['min_value'] = min(data['values'])
                aggregate['max_value'] = max(data['values'])

            result.append(aggregate)

        return result

    def _save_aggregates(self, aggregates: List[Dict[str, Any]], date: datetime.date):
        """Save aggregates to database"""
        for aggregate_data in aggregates:
            aggregate = EventAggregate(
                date=date,
                **aggregate_data
            )
            db.session.merge(aggregate)  # Use merge to update if exists

        db.session.commit()

    def get_user_metrics_summary(
            self,
            user_id: int,
            start_date: datetime.date,
            end_date: datetime.date
    ) -> Dict[str, Any]:
        """Get summarized metrics for a user over a date range"""

        aggregates = db.session.query(EventAggregate).filter(
            EventAggregate.user_id == user_id,
            EventAggregate.date >= start_date,
            EventAggregate.date <= end_date
        ).all()

        summary = {
            'total_events': sum(a.count for a in aggregates),
            'unique_event_types': len(set(a.event_name for a in aggregates)),
            'daily_average': sum(a.count for a in aggregates) / max(1, (end_date - start_date).days),
            'events_by_type': {},
            'trends': []
        }

        # Group by event type
        for aggregate in aggregates:
            if aggregate.event_name not in summary['events_by_type']:
                summary['events_by_type'][aggregate.event_name] = 0
            summary['events_by_type'][aggregate.event_name] += aggregate.count

        return summary