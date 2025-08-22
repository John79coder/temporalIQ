# tests/analytics/test_analytics_system.py
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import Mock, patch
from flask import g
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from app.analytics.models.entities import UserEvent, EventAggregate
from app.analytics.services.event_tracker import EventTracker
from app.analytics.services.metrics_aggregator import MetricsAggregator
from app.analytics.repositories.event_repository import EventRepository
from app.analytics.models.schemas import (
    UserEventIn,
    TaskEventProperties, SyncEventProperties
)
from app.utils.exceptions import DatabaseError
from config import TestingConfig


class TestEventTracker:
    """Test suite for EventTracker service"""

    @pytest.fixture
    def event_tracker(self):
        """Create an EventTracker instance"""
        tracker = EventTracker()
        tracker.event_buffer = []  # Clear buffer
        return tracker

    def test_track_event_basic(self, event_tracker, db_session):
        """Test basic event tracking"""
        # Track an event
        event_tracker.track(
            user_id=1,
            event_name="test_event",
            properties={"key": "value"},
            timestamp=datetime.utcnow()
        )

        # Check buffer
        assert len(event_tracker.event_buffer) == 1
        event = event_tracker.event_buffer[0]
        assert event.user_id == 1
        assert event.event_name == "test_event"
        assert event.properties["key"] == "value"

    def test_track_event_auto_flush(self, event_tracker, db_session):
        """Test automatic buffer flush when reaching batch size"""
        # Set small batch size for testing
        event_tracker.batch_size = 2

        with patch.object(db.session, 'bulk_save_objects') as mock_bulk_save:
            with patch.object(db.session, 'commit') as mock_commit:
                # Track events up to batch size
                event_tracker.track(user_id=1, event_name="event1")
                assert len(event_tracker.event_buffer) == 1

                # This should trigger flush
                event_tracker.track(user_id=1, event_name="event2")

                # Buffer should be cleared after flush
                assert len(event_tracker.event_buffer) == 0
                mock_bulk_save.assert_called_once()
                mock_commit.assert_called_once()

    def test_track_task_scheduled(self, event_tracker):
        """Test tracking task scheduled event"""
        event_tracker.track_task_scheduled(
            user_id=1,
            task_id=100,
            calendar_id="cal_123"
        )

        assert len(event_tracker.event_buffer) == 1
        event = event_tracker.event_buffer[0]
        assert event.event_name == "task_scheduled"
        assert event.properties["task_id"] == 100
        assert event.properties["calendar_id"] == "cal_123"

    def test_track_notion_connected(self, event_tracker):
        """Test tracking Notion connection event"""
        event_tracker.track_notion_connected(
            user_id=1,
            database_count=5
        )

        assert len(event_tracker.event_buffer) == 1
        event = event_tracker.event_buffer[0]
        assert event.event_name == "notion_connected"
        assert event.properties["database_count"] == 5

    def test_track_feature_usage(self, event_tracker):
        """Test tracking feature usage event"""
        event_tracker.track_feature_usage(
            user_id=1,
            feature_name="ai_mapping",
            metadata={"accuracy": 0.95}
        )

        assert len(event_tracker.event_buffer) == 1
        event = event_tracker.event_buffer[0]
        assert event.event_name == "feature_used"
        assert event.properties["feature_name"] == "ai_mapping"
        assert event.properties["accuracy"] == 0.95

    def test_track_sync_event_success(self, event_tracker):
        """Test tracking successful sync event"""
        event_tracker.track_sync_event(
            user_id=1,
            sync_type="notion",
            success=True,
            duration_ms=1500.5
        )

        assert len(event_tracker.event_buffer) == 1
        event = event_tracker.event_buffer[0]
        assert event.event_name == "sync_notion"
        assert event.properties["success"] is True
        assert event.properties["duration_ms"] == 1500.5
        assert event.properties["error_message"] is None

    def test_track_sync_event_failure(self, event_tracker):
        """Test tracking failed sync event"""
        event_tracker.track_sync_event(
            user_id=1,
            sync_type="icloud",
            success=False,
            duration_ms=500.0,
            error_message="Connection timeout"
        )

        assert len(event_tracker.event_buffer) == 1
        event = event_tracker.event_buffer[0]
        assert event.event_name == "sync_icloud"
        assert event.properties["success"] is False
        assert event.properties["error_message"] == "Connection timeout"

    def test_flush_empty_buffer(self, event_tracker, db_session):
        """Test flushing empty buffer does nothing"""
        with patch.object(db.session, 'bulk_save_objects') as mock_bulk_save:
            event_tracker.flush()
            mock_bulk_save.assert_not_called()

    def test_flush_with_database_error(self, event_tracker, db_session):
        """Test flush handles database errors gracefully"""
        # Add an event to buffer
        event_tracker.track(user_id=1, event_name="test")

        with patch.object(db.session, 'bulk_save_objects', side_effect=SQLAlchemyError("DB Error")):
            with patch('app.analytics.services.event_tracker.ApplicationLogger') as mock_logger:
                # Should not raise, just log error
                event_tracker.flush()

                # Buffer should be cleared even on error
                assert len(event_tracker.event_buffer) == 0

    def test_get_user_metrics(self, event_tracker, db_session):
        """Test getting user metrics"""
        # Create test events
        now = datetime.utcnow()
        events = [
            UserEvent(
                user_id=1,
                event_name="task_scheduled",
                properties={},
                timestamp=now - timedelta(days=1)
            ),
            UserEvent(
                user_id=1,
                event_name="task_scheduled",
                properties={},
                timestamp=now - timedelta(days=2)
            ),
            UserEvent(
                user_id=1,
                event_name="sync_notion",
                properties={"success": True},
                timestamp=now - timedelta(days=1)
            ),
            UserEvent(
                user_id=1,
                event_name="sync_notion",
                properties={"success": False},
                timestamp=now - timedelta(days=3)
            ),
            UserEvent(
                user_id=1,
                event_name="feature_used",
                properties={"feature_name": "ai_mapping"},
                timestamp=now - timedelta(hours=12)
            )
        ]

        with patch.object(db.session, 'query') as mock_query:
            mock_filter = Mock()
            mock_filter.all.return_value = events
            mock_query.return_value.filter.return_value = mock_filter

            metrics = event_tracker.get_user_metrics(user_id=1, days=7)

            assert metrics["total_events"] == 5
            assert metrics["unique_event_types"] == 3
            assert metrics["tasks_scheduled"] == 2
            assert metrics["sync_success_rate"] == 50.0  # 1 success, 1 failure
            assert len(metrics["most_used_features"]) == 1
            assert metrics["most_used_features"][0]["feature"] == "ai_mapping"


class TestMetricsAggregator:
    """Test suite for MetricsAggregator service"""

    @pytest.fixture
    def metrics_aggregator(self):
        """Create a MetricsAggregator instance"""
        return MetricsAggregator()

    def test_run_aggregation(self, metrics_aggregator, db_session):
        """Test running metrics aggregation"""
        test_date = date.today() - timedelta(days=1)

        # Mock events for aggregation
        mock_events = [
            UserEvent(user_id=1, event_name="task_scheduled", properties={},
                      timestamp=datetime.combine(test_date, datetime.min.time())),
            UserEvent(user_id=1, event_name="task_scheduled", properties={},
                      timestamp=datetime.combine(test_date, datetime.min.time())),
            UserEvent(user_id=2, event_name="sync_notion", properties={"value": 100},
                      timestamp=datetime.combine(test_date, datetime.min.time())),
            UserEvent(user_id=2, event_name="sync_notion", properties={"value": 200},
                      timestamp=datetime.combine(test_date, datetime.min.time())),
        ]

        with patch.object(metrics_aggregator, '_get_events_for_date', return_value=mock_events):
            with patch.object(db.session, 'merge') as mock_merge:
                with patch.object(db.session, 'commit') as mock_commit:
                    metrics_aggregator.run_aggregation(test_date)

                    # Should create aggregates for each user/event combination
                    assert mock_merge.call_count == 2  # 2 unique user/event combinations
                    mock_commit.assert_called_once()

    def test_compute_aggregates(self, metrics_aggregator):
        """Test computing aggregates from events"""
        events = [
            UserEvent(user_id=1, event_name="event1", properties={"value": 10}, timestamp=datetime.utcnow()),
            UserEvent(user_id=1, event_name="event1", properties={"value": 20}, timestamp=datetime.utcnow()),
            UserEvent(user_id=1, event_name="event2", properties={}, timestamp=datetime.utcnow()),
            UserEvent(user_id=2, event_name="event1", properties={"value": 30}, timestamp=datetime.utcnow()),
        ]

        aggregates = metrics_aggregator._compute_aggregates(events)

        assert len(aggregates) == 3  # 3 unique user/event combinations

        # Check user 1, event1 aggregate
        user1_event1 = next(a for a in aggregates if a['user_id'] == 1 and a['event_name'] == 'event1')
        assert user1_event1['count'] == 2
        assert user1_event1['sum_value'] == 30
        assert user1_event1['avg_value'] == 15
        assert user1_event1['min_value'] == 10
        assert user1_event1['max_value'] == 20

    def test_get_user_metrics_summary(self, metrics_aggregator, db_session):
        """Test getting user metrics summary"""
        start_date = date.today() - timedelta(days=7)
        end_date = date.today()

        mock_aggregates = [
            EventAggregate(user_id=1, date=start_date, event_name="task_scheduled", count=5),
            EventAggregate(user_id=1, date=start_date + timedelta(days=1), event_name="task_scheduled", count=3),
            EventAggregate(user_id=1, date=start_date, event_name="sync_notion", count=2),
        ]

        with patch.object(db.session, 'query') as mock_query:
            mock_filter = Mock()
            mock_filter.all.return_value = mock_aggregates
            mock_query.return_value.filter.return_value = mock_filter

            summary = metrics_aggregator.get_user_metrics_summary(
                user_id=1,
                start_date=start_date,
                end_date=end_date
            )

            assert summary['total_events'] == 10  # 5 + 3 + 2
            assert summary['unique_event_types'] == 2
            assert summary['events_by_type']['task_scheduled'] == 8
            assert summary['events_by_type']['sync_notion'] == 2


class TestEventRepository:
    """Test suite for EventRepository"""

    @pytest.fixture
    def event_repo(self):
        """Create an EventRepository instance"""
        return EventRepository()

    def test_create_event(self, event_repo, db_session):
        """Test creating a single event"""
        event_data = {
            'user_id': 1,
            'event_name': 'test_event',
            'properties': {'key': 'value'},
            'timestamp': datetime.utcnow()
        }

        with patch.object(db_session, 'add') as mock_add:
            with patch.object(db_session, 'commit') as mock_commit:
                with patch.object(db_session, 'refresh') as mock_refresh:
                    event = event_repo.create_event(db_session, event_data)

                    mock_add.assert_called_once()
                    mock_commit.assert_called_once()
                    mock_refresh.assert_called_once()

    def test_create_event_database_error(self, event_repo, db_session):
        """Test handling database error when creating event"""
        event_data = {'user_id': 1, 'event_name': 'test'}

        with patch.object(db_session, 'add', side_effect=SQLAlchemyError("DB Error")):
            with pytest.raises(DatabaseError) as exc_info:
                event_repo.create_event(db_session, event_data)

            assert "Failed to create event" in str(exc_info.value)

    def test_get_user_events_with_filters(self, event_repo, db_session):
        """Test getting user events with various filters"""
        mock_query = Mock()
        mock_filter = Mock()
        mock_order = Mock()
        mock_limit = Mock()

        mock_query.filter.return_value = mock_filter
        mock_filter.filter.return_value = mock_filter
        mock_filter.order_by.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        mock_limit.all.return_value = []

        with patch.object(db_session, 'query', return_value=mock_query):
            events = event_repo.get_user_events(
                db=db_session,
                user_id=1,
                start_date=datetime.utcnow() - timedelta(days=7),
                end_date=datetime.utcnow(),
                event_names=['event1', 'event2'],
                limit=100
            )

            # Verify filters were applied
            assert mock_query.filter.called
            assert mock_filter.filter.called
            assert mock_order.limit.called_with(100)

    def test_count_events(self, event_repo, db_session):
        """Test counting events"""
        with patch.object(db_session, 'query') as mock_query:
            mock_filter = Mock()
            mock_filter.scalar.return_value = 42
            mock_query.return_value.filter.return_value = mock_filter

            count = event_repo.count_events(
                db=db_session,
                user_id=1,
                event_name="test_event"
            )

            assert count == 42

    def test_delete_old_events(self, event_repo, db_session):
        """Test deleting old events"""
        with patch.object(db_session, 'query') as mock_query:
            mock_filter = Mock()
            mock_filter.delete.return_value = 100  # Number of deleted records
            mock_query.return_value.filter.return_value = mock_filter

            with patch.object(db_session, 'commit'):
                deleted_count = event_repo.delete_old_events(
                    db=db_session,
                    days_to_keep=30
                )

                assert deleted_count == 100


class TestAnalyticsAPI:
    """Test suite for analytics API endpoints"""

    def test_track_event_endpoint(self, authorized_client, db_session, test_user):
        """Test POST /analytics/events endpoint"""
        user, user_id = test_user

        event_data = {
            "user_id": user_id,
            "event_name": "test_event",
            "properties": {"key": "value"}
        }

        with patch('app.analytics.routes.api.event_tracker.track') as mock_track:
            response = authorized_client.post(
                "/analytics/events",
                json=event_data,
                headers={"X-CSRF-Token": authorized_client.csrf_token}
            )

            assert response.status_code == 201
            assert response.json["status"] == "tracked"
            mock_track.assert_called_once()

    def test_track_event_unauthorized_user(self, authorized_client, db_session, test_user):
        """Test that users can't track events for other users"""
        user, user_id = test_user

        event_data = {
            "user_id": 999,  # Different user ID
            "event_name": "test_event",
            "properties": {}
        }

        response = authorized_client.post(
            "/analytics/events",
            json=event_data,
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )

        assert response.status_code == 403
        assert "Unauthorized" in response.json["error"]

    def test_track_batch_events(self, authorized_client, db_session, test_user):
        """Test POST /analytics/events/batch endpoint"""
        user, user_id = test_user

        batch_data = {
            "events": [
                {"user_id": user_id, "event_name": "event1", "properties": {}},
                {"user_id": user_id, "event_name": "event2", "properties": {}},
                {"user_id": 999, "event_name": "event3", "properties": {}},  # Should be skipped
            ]
        }

        with patch('app.analytics.routes.api.event_tracker.track') as mock_track:
            with patch('app.analytics.routes.api.event_tracker.flush') as mock_flush:
                response = authorized_client.post(
                    "/analytics/events/batch",
                    json=batch_data,
                    headers={"X-CSRF-Token": authorized_client.csrf_token}
                )

                assert response.status_code == 201
                assert response.json["events_tracked"] == 2  # Only 2 events for current user
                mock_flush.assert_called_once()

    def test_batch_events_invalid_size(self, authorized_client, test_user):
        """Test batch endpoint with invalid batch size"""
        user, user_id = test_user

        # Too many events
        batch_data = {
            "events": [{"user_id": user_id, "event_name": f"event{i}", "properties": {}}
                       for i in range(101)]
        }

        response = authorized_client.post(
            "/analytics/events/batch",
            json=batch_data,
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )

        assert response.status_code == 400
        assert "Invalid batch size" in response.json["error"]

    def test_get_user_metrics(self, authorized_client, db_session, test_user):
        """Test GET /analytics/metrics/<user_id> endpoint"""
        user, user_id = test_user

        mock_metrics = {
            "total_events": 100,
            "unique_event_types": 5,
            "tasks_scheduled": 20,
            "sync_success_rate": 95.0,
            "most_used_features": [],
            "activity_by_day": {}
        }

        with patch('app.analytics.routes.api.event_tracker.get_user_metrics', return_value=mock_metrics):
            response = authorized_client.get(
                f"/analytics/metrics/{user_id}?days=30",
                headers={"X-CSRF-Token": authorized_client.csrf_token}
            )

            assert response.status_code == 200
            assert response.json["total_events"] == 100
            assert response.json["sync_success_rate"] == 95.0

    def test_get_metrics_summary(self, authorized_client, db_session, test_user):
        """Test GET /analytics/metrics/<user_id>/summary endpoint"""
        user, user_id = test_user

        mock_summary = {
            "total_events": 500,
            "unique_event_types": 10,
            "daily_average": 16.7,
            "events_by_type": {"task_scheduled": 100},
            "trends": []
        }

        with patch('app.analytics.routes.api.metrics_aggregator.get_user_metrics_summary', return_value=mock_summary):
            response = authorized_client.get(
                f"/analytics/metrics/{user_id}/summary?start_date=2024-01-01&end_date=2024-01-31",
                headers={"X-CSRF-Token": authorized_client.csrf_token}
            )

            assert response.status_code == 200
            assert response.json["total_events"] == 500

    def test_get_user_events(self, authorized_client, db_session, test_user):
        """Test GET /analytics/events/<user_id> endpoint"""
        user, user_id = test_user

        mock_events = [
            UserEvent(id=1, user_id=user_id, event_name="test", properties={}, timestamp=datetime.utcnow())
        ]

        with patch('app.analytics.repositories.event_repository.EventRepository.get_user_events',
                   return_value=mock_events):
            response = authorized_client.get(
                f"/analytics/events/{user_id}?limit=10&event_name=test",
                headers={"X-CSRF-Token": authorized_client.csrf_token}
            )

            assert response.status_code == 200
            assert len(response.json) == 1


class TestEventSchemas:
    """Test suite for event schemas validation"""

    def test_user_event_in_validation(self):
        """Test UserEventIn schema validation"""
        # Valid event
        valid_data = {
            "user_id": 1,
            "event_name": "Test Event",
            "properties": {"key": "value"}
        }
        event = UserEventIn(**valid_data)
        assert event.event_name == "test_event"  # Should be normalized

        # Invalid event name (too long)
        invalid_data = {
            "user_id": 1,
            "event_name": "x" * 101,
            "properties": {}
        }
        with pytest.raises(ValueError):
            UserEventIn(**invalid_data)

    def test_task_event_properties(self):
        """Test TaskEventProperties schema"""
        props = TaskEventProperties(
            task_id=1,
            task_title="Test Task",
            calendar_id="cal_123",
            duration_minutes=30,
            priority="high"
        )
        assert props.task_id == 1
        assert props.duration_minutes == 30

    def test_sync_event_properties(self):
        """Test SyncEventProperties schema"""
        props = SyncEventProperties(
            sync_type="notion",
            success=True,
            duration_ms=1500.5,
            items_synced=10
        )
        assert props.sync_type == "notion"
        assert props.success is True
        assert props.items_synced == 10


class TestAnalyticsIntegration:
    """Integration tests for analytics with other modules"""

    def test_analytics_with_notion_connection(self, authorized_client, db_session, test_user):
        """Test that Notion connection triggers analytics event"""
        user, user_id = test_user

        with patch('app.notion.auth.service.NotionAuthService.store_access_token'):
            from app.analytics.services.event_tracker import EventTracker
            tracker = EventTracker()
            tracker.track_notion_connected(user_id=user_id, database_count=3)

            assert len(tracker.event_buffer) == 1
            assert tracker.event_buffer[0].event_name == "notion_connected"

    def test_analytics_with_task_scheduling(self, test_user):
        from app.analytics.services.event_tracker import EventTracker
        user, user_id = test_user

        tracker = EventTracker()
        tracker.track_task_scheduled(
            user_id=user_id,
            task_id=123,
            calendar_id="cal_abc"
        )

        assert len(tracker.event_buffer) == 1
        event = tracker.event_buffer[0]
        assert event.event_name == "task_scheduled"
        assert event.properties["task_id"] == 123
        assert event.properties["calendar_id"] == "cal_abc"


# Fixtures for analytics tests
@pytest.fixture(scope='function')
def app():
    """Create application for testing"""
    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db_session(app):
    """Get database session"""
    with app.app_context():
        yield db.session


@pytest.fixture
def test_user(db_session, authentication_service):
    """Create a test user"""
    from app.auth.models.entities import User
    import uuid

    email = f"test_{uuid.uuid4().hex}@example.com"
    user = authentication_service.create_user(
        db_session,
        email,
        "TestPassword123!"
    )
    db_session.commit()
    return user, user.id


@pytest.fixture
def authentication_service(app):
    """Get authentication service"""
    with app.app_context():
        return app.extensions['app_context'].get_service('authentication_service')


@pytest.fixture
def authorized_client(app, test_user):
    """Create an authorized test client with JWT token"""
    from flask_jwt_extended import create_access_token
    from tests.utils.custom_client import CSRFClient

    app.test_client_class = CSRFClient
    client = app.test_client()

    user, user_id = test_user

    with app.app_context():
        # Create JWT token
        access_token = create_access_token(
            identity=str(user_id),
            additional_claims={"is_verified": True}
        )

        # Set authorization header
        client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'

        # Mock current user in g
        with client.session_transaction() as sess:
            sess['user_id'] = user_id

        # Patch g.current_user for the requests
        def _push_current_user():
            g.current_user = user

        app.before_request_funcs.setdefault(None, []).append(_push_current_user)

    return client


if __name__ == "__main__":
    pytest.main([__file__, "-v"])