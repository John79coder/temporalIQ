# tests/scheduling/test_routes.py
from unittest.mock import patch, Mock
from flask import g
from app.scheduling.models.entities import Task
from app.auth.models.entities import User
from app.notion.models.entities import TaskCandidate
from app.user_preferences.models.entities import UserPreferences


@patch("app.icloud.services.event_service.CalDAVEventService.fetch_user_events")
def test_preview_schedule_success(mock_fetch_user_events, authorized_client, db_session, app, test_user):
    _, user_id = test_user
    mock_fetch_user_events.return_value = []
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)
        db_session.add(TaskCandidate(user_id=user_id, notion_db_id="db1", title="Test Task", duration=30, confidence=1.0, due_date=None, issues=[]))
        db_session.add(UserPreferences(user_id=user_id, time_zone="UTC", work_hours=8.0, block_size_minutes=30))
        db_session.commit()


        payload = {
            "user_id": user_id,
            "notion_db_id": "db1",
            "calendar_id": "cal1",
            "start_date": "2025-07-12T00:00:00Z",
            "end_date": "2025-07-12T23:59:59Z",
            "earliest_time": "09:00",
            "latest_time": "17:00"
        }


        response = authorized_client.post(
            "/scheduling/preview",
            json=payload,
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )
        assert response.status_code == 200
        assert "time_blocks" in response.json

@patch("app.icloud.services.client_manager.CalDAVClientManager.get_caldav_client_for_user")
@patch("app.icloud.services.event_service.CalDAVEventService.write_scheduled_event")
def test_confirm_schedule_success(mock_get_caldav_client, mock_write_scheduled_event, authorized_client, db_session, app, test_user):
    _, user_id = test_user
    mock_get_caldav_client.return_value = Mock()  # Mock the CalDAV client
    mock_write_scheduled_event.return_value = None
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)
        task = Task(user_id=user_id, notion_db_id="db1", title="Test Task", duration=30)
        db_session.add(task)
        db_session.commit()
        payload = {
            "user_id": user_id,
            "calendar_id": "cal1",
            "time_blocks": [
                {
                    "user_id": user_id,
                    "calendar_id": "cal1",
                    "start": "2025-07-12T09:00:00Z",
                    "end": "2025-07-12T09:30:00Z",
                    "task_id": task.id
                }
            ]
        }
        response = authorized_client.post(
            "/scheduling/confirm",
            json=payload,
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )
        assert response.status_code == 200
        assert response.json["message"] == "Schedule confirmed and written to iCloud."