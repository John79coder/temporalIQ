# tests/scheduling/test_routes_with_learning.py
from unittest.mock import patch, Mock
from flask import g
from app.scheduling.models.entities import Task
from app.auth.models.entities import User
from app.user_preferences.models.entities import UserPreferences
from app.features.models.entities import AITrainingEvent
from app.features.models.schemas import DurationLogInput, DurationLogLabel, SlotChoiceInput, SlotChoiceLabel
from app.notion.models.entities import TaskCandidate
import random


@patch("app.icloud.services.event_service.CalDAVEventService.fetch_user_events")
def test_preview_schedule_success(mock_fetch_user_events, authorized_client, db_session, app, test_user):
    _, user_id = test_user
    mock_fetch_user_events.return_value = []
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)
        db_session.add(TaskCandidate(user_id=user_id, notion_db_id="db1", title="Test Task", duration=30, confidence=1.0, due_date=None, issues=[]))
        db_session.add(UserPreferences(user_id=user_id, time_zone="UTC", work_hours=8.0, block_size_minutes=30))
        # Seed varied duration_log events for FreeTimeFinder Ridge training
        random.seed(42)  # Reproducible results
        for i in range(100):
            num_events = random.randint(1, 10)
            day_length_hours = random.uniform(6.0, 10.0)
            urgency = random.uniform(0.1, 1.0)
            duration = max(15, min(120, 20 + (30 * urgency) - (2 * num_events) + (5 * day_length_hours) + random.uniform(-10, 10)))
            db_session.add(AITrainingEvent(
                user_id=user_id,
                task_id=None,
                event_type='duration_log',
                input_json=DurationLogInput(
                    num_events=num_events,
                    day_length_hours=day_length_hours,
                    urgency=urgency
                ).model_dump(),
                label_json=DurationLogLabel(duration_minutes=duration).model_dump(),
                source='test'
            ))
        # Seed varied slot_choice events for TaskPrioritizer Ridge training
        for i in range(100):
            slot_start = f"2025-07-12T{random.randint(0, 23):02d}:{random.randint(0, 59):02d}:00Z"
            urgency_float = random.uniform(0.0, 1.0)  # CHANGED: Use float directly
            duration = random.randint(15, 120)
            selected = random.choice([True, False])
            db_session.add(AITrainingEvent(
                user_id=user_id,
                task_id=None,
                event_type='slot_choice',
                input_json=SlotChoiceInput(
                    slot_start=slot_start,
                    urgency=urgency_float,  # CHANGED: Now float
                    duration=duration
                ).model_dump(),
                label_json=SlotChoiceLabel(selected=selected).model_dump(),
                source='test'
            ))
        db_session.commit()
        # Verify seeding
        duration_count = db_session.query(AITrainingEvent).filter_by(user_id=user_id, event_type='duration_log').count()
        slot_count = db_session.query(AITrainingEvent).filter_by(user_id=user_id, event_type='slot_choice').count()
        print(f"Seeded {duration_count} duration_log events and {slot_count} slot_choice events for user_id {user_id}")

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
    mock_get_caldav_client.return_value = Mock()
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