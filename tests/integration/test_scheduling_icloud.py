import json
from unittest.mock import Mock
from unittest.mock import patch
from flask import g
from app.icloud.models.entities import iCloudConnection
from app.auth.models.entities import User
from app.notion.models.entities import TaskCandidate
from datetime import datetime, timezone
from app.utils.encryption import Encryptor
from app.utils.time_zone import TimeZone


@patch('app.icloud.services.event_service.CalDAVEventService.fetch_user_events')
@patch('app.icloud.services.client_manager.CalDAVClientManager.get_caldav_client_for_user')
def test_scheduling_preview(mock_get_caldav_client, mock_fetch_user_events, authorized_client, app, db_session, test_user):
    user, user_id = test_user
    mock_fetch_user_events.return_value = []  # Mock fetch_user_events to return empty list
    mock_get_caldav_client.return_value = Mock()  # Mock CalDAV client to avoid decryption

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)

        # Create a valid encrypted password
        encryptor = Encryptor()
        valid_encrypted_password = encryptor.encrypt("Secure123!")

        # Insert a mock iCloud connection
        mock_connection = iCloudConnection(
            user_id=user_id,
            encrypted_app_password=valid_encrypted_password,
            created_at=datetime.now(timezone.utc),
            is_active=True
        )
        db_session.add(mock_connection)

        # Insert a TaskCandidate to ensure tasks are available
        task_candidate = TaskCandidate(
            user_id=user_id,
            notion_db_id="db1",
            title="Test Task",
            due_date=datetime(2025, 7, 12, 9, 0, tzinfo=timezone.utc),
            duration=30,
            confidence=0.9,
        )
        db_session.add(task_candidate)
        db_session.commit()

        start_time = TimeZone.serialize_datetime(datetime(2025, 7, 12, tzinfo=timezone.utc))
        end_time =  TimeZone.serialize_datetime(datetime(2025, 7, 12, tzinfo=timezone.utc))

        payload = {
            "user_id": user_id,
            "notion_db_id": "db1",
            "calendar_id": "cal1",
            "start_date": start_time,
            "end_date": end_time,
            "earliest_time": "09:00",
            "latest_time": "17:00"
        }

        response = authorized_client.post(
            "/scheduling/preview",
            data=json.dumps(payload),  # <-- Use raw JSON string, not dict
            content_type="application/json",
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )

        assert response.status_code == 200
        assert "time_blocks" in response.json