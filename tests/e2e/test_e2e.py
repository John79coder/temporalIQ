# tests/e2e/test_e2e.py
from datetime import timedelta, datetime
from unittest.mock import Mock, patch

import pytz
from pydantic import HttpUrl

from app.features.models.schemas import AISettingsUpdate
from app.icloud.models.schemas import TimeBlock
from app.notion.models.entities import TaskCandidate
from app.user_preferences.models.entities import UserPreferences
from app.utils.time_zone import TimeZone


@patch("requests.sessions.Session.post")
@patch("app.notion.client.notion_client.NotionClient.fetch_schema")
@patch("app.notion.client.notion_client.NotionClient.fetch_rows")
@patch("app.icloud.services.event_service.CalDAVEventService.fetch_user_events")
@patch("app.icloud.services.event_service.CalDAVEventService.write_scheduled_event")
@patch("app.icloud.client.caldav_client.CalDAVClient.__init__", return_value=None)
@patch("app.icloud.client.caldav_client.CalDAVClient.list_calendars", return_value=[])
@patch("app.utils.encryption.Encryptor.encrypt", return_value="test-encrypted")
@patch("app.utils.time_zone.TimeZone.utc_now", return_value=datetime(2025, 7, 18, tzinfo=pytz.UTC))  # Make 07-19 "future"
def test_full_user_flow_mapping_to_calendar_write(
        mock_utc_now,  # New patch for utc_now
        mock_encrypt,
        mock_list_calendars,
        mock_caldav_init,
        mock_write_event,
        mock_fetch_events,
        mock_fetch_rows,
        mock_fetch_schema,
        mock_requests_post,
        authorized_client,
        db_session,
        app,
        test_user,
        features_service):
    mock_fetch_schema.return_value = {"Title": {"type": "title"}, "Due": {"type": "date"},
                                      "Duration": {"type": "number"}}
    mock_fetch_rows.return_value = [
        {
            "properties": {
                "Title": {"title": [{"plain_text": "Test Task"}]},
                "Due": {"date": {"start": "2025-07-20T00:00:00Z"}},
                "Duration": {"number": 30},  # Changed to 30min to fit in single slot
            }
        }
    ]
    mock_fetch_events.return_value = [] # No existing events, all slots free
    mock_requests_post.return_value = Mock(
        status_code=200,
        json=lambda: {
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "expires_in": 3600,
            "workspace_id": "test-workspace",
        },
    )
    mock_write_event.return_value = "test-uid"

    user, user_id = test_user

    # Add preferences and settings to avoid errors
    preferences = UserPreferences(
        user_id=user_id,
        work_hours=8.0,
        time_zone="UTC"
    )
    db_session.add(preferences)

    with patch("app.features.services.service.SubscriptionsService.is_premium", return_value=True):
        features_service.update_settings(db_session, user_id, AISettingsUpdate(
            use_llm_mapping=False,
            use_learned_detector=False,
            use_spacy_heuristics=False,
            use_embedding_similarity=False,
            use_ml_prioritization=False,
            use_nlp_urgency=False,
            use_rl_optimization=False,
            urgency_learning_scope='off',
            duration_learning_scope='off',
            mapping_learning_scope='off',
            slot_ranking_learning_scope='off'))

    with app.app_context():
        # Step 1: Connect to Notion
        notion_connect_response = authorized_client.post(
            "/notion/connect",
            json={
                "user_id": user_id,
                "code": "test-code",
                "redirect_uri": str(HttpUrl("http://localhost")),
            },
            headers={"X-CSRF-Token": authorized_client.csrf_token},
        )
        assert notion_connect_response.status_code == 200

        # Step 2: Map schema
        map_schema_response = authorized_client.post(
            "/notion/map-schema",
            json={
                "user_id": user_id,
                "notion_db_id": "db1",
                "title_field": "Title",
                "due_date_field": "Due",
                "duration_field": "Duration",
            },
            headers={"X-CSRF-Token": authorized_client.csrf_token},
        )
        assert map_schema_response.status_code == 200

        # Step 3: Generate candidates
        generate_candidates_response = authorized_client.post(
            "/notion/generate-candidates", json={"database_id": "db1"},
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )
        assert generate_candidates_response.status_code == 200
        assert len(generate_candidates_response.json) == 1
        assert generate_candidates_response.json[0]["title"] == "Test Task"

        # Step 4: Connect to iCloud (required for scheduling)
        icloud_connect_response = authorized_client.post(
            "/icloud/connect",
            json={"app_password": "test-app-password"},
            headers={"X-CSRF-Token": authorized_client.csrf_token},
        )
        assert icloud_connect_response.status_code == 200

        # Step 5: Preview scheduling
        preview_response = authorized_client.post(
            "/scheduling/preview",
            json={
                "user_id": user_id,
                "notion_db_id": "db1",
                "calendar_id": "cal1",
                "start_date": "2025-07-19T00:00:00Z",
                "end_date": "2025-07-19T23:59:59Z",
                "earliest_time": "09:00",
                "latest_time": "17:00",
            },
            headers={"X-CSRF-Token": authorized_client.csrf_token},
        )
        assert preview_response.status_code == 200
        time_blocks = preview_response.json["time_blocks"]
        assert len(time_blocks) > 0 # At least one block generated

        # Step 6: Confirm scheduling
        confirm_time_blocks = [
            {
                "start": tb["start"],
                "end": tb["end"],
                "task_id": tb["task_id"] if tb["task_id"] is not None else None,
            }
            for tb in time_blocks
        ]
        confirm_response = authorized_client.post(
            "/scheduling/confirm",
            json={"user_id": user_id, "calendar_id": "cal1", "time_blocks": confirm_time_blocks},
            headers={"X-CSRF-Token": authorized_client.csrf_token},
        )
        assert confirm_response.status_code == 200
        assert mock_write_event.call_count == sum(1 for tb in confirm_time_blocks if tb["task_id"] is not None)

def test_api_schedule_preview_time_blocks(authorized_client, db_session, app, test_user, features_service):
    user, user_id = test_user

    # Add preferences and settings
    preferences = UserPreferences(
        user_id=user_id,
        work_hours=8.0,
        time_zone="UTC"
    )
    db_session.add(preferences)

    with patch("app.features.services.service.SubscriptionsService.is_premium", return_value=True):
        features_service.update_settings(db_session, user_id, AISettingsUpdate(
            use_llm_mapping=False,
            use_learned_detector=False,
            use_spacy_heuristics=False,
            use_embedding_similarity=False,
            use_ml_prioritization=False,
            use_nlp_urgency=False,
            use_rl_optimization=False,
            urgency_learning_scope='off',
            duration_learning_scope='off',
            mapping_learning_scope='off',
            slot_ranking_learning_scope='off'))

    ###################################The records are already in the db... Use an appropriate Service and update.

    candidate = TaskCandidate(
        user_id=user_id,
        notion_db_id="db1",
        title="Test task",
        due_date=TimeZone.utc_now() + timedelta(days=1),
        duration=30,
        confidence=0.9,
        priority=None,  # Set to None to avoid str/float issue
        status="not started",
        created_at=TimeZone.utc_now(),
        updated_at=TimeZone.utc_now()
    )
    db_session.add(candidate)
    db_session.commit()

    # 💡 Query the real task from the DB after generate_time_blocks creates it
    def prioritize_passthrough(tasks, db):
        return tasks

    with patch('app.scheduling.services.task_prioritizer.TaskPrioritizer.prioritize_tasks',
               side_effect=prioritize_passthrough):
        with patch('app.scheduling.services.free_time_finder.FreeTimeFinder.find_free_slots', return_value=[
            TimeBlock(
                start=TimeZone.utc_now(),
                end=TimeZone.utc_now() + timedelta(hours=1),
                user_id=user_id,
                calendar_id="cal1"
            )
        ]):
            with patch("app.utils.encryption.Encryptor.encrypt", return_value="test-encrypted"):
                # Connect to iCloud first
                icloud_connect_response = authorized_client.post(
                    "/icloud/connect",
                    json={"app_password": "test-app-password"},
                    headers={"X-CSRF-Token": authorized_client.csrf_token},
                )
                assert icloud_connect_response.status_code == 200

                response = authorized_client.post(
                    "/scheduling/preview",
                    json={
                        "user_id": user_id,
                        "notion_db_id": "db1",
                        "calendar_id": "cal1",
                        "start_date": "2025-07-19T00:00:00Z",
                        "end_date": "2025-07-19T23:59:59Z",
                        "earliest_time": "09:00",
                        "latest_time": "17:00"
                    },
                    headers={"X-CSRF-Token": authorized_client.csrf_token}
                )

                assert response.status_code == 200

                blocks = response.json["time_blocks"]

                assert isinstance(blocks, list)
                assert len(blocks) > 0
                assert "start" in blocks[0]
                assert "end" in blocks[0]
