# tests/notion/test_notion_routes.py
from unittest.mock import patch, MagicMock
from flask import g
from pydantic import HttpUrl
from app.notion.models.entities import NotionConnection, FieldMapping
from app.auth.models.entities import User
from datetime import datetime, timezone
from app.utils.exceptions import DatabaseError
from app.utils.exceptions import NotionError


def test_manual_auth_error_triggers_handler(client):

    response = client.get("/__test_auth_error")

    assert response.status_code == 401
    assert response.json["title"] == "AuthError"
    assert "Manual test" in response.json["detail"]


@patch("app.notion.auth.service.requests.sessions.Session.post")
def test_connect_notion_success(mock_post, authorized_client, db_session, app, test_user, encryptor):

    _, user_id = test_user

    mock_post.return_value.json.return_value = {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "expires_in": 3600,
        "workspace_id": "ws1"
    }

    mock_post.return_value.raise_for_status = lambda: None

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)

        response = authorized_client.post("/notion/connect", json={
            "user_id": user_id,
            "code": "test-code",
            "redirect_uri": str(HttpUrl("http://localhost"))
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200
        assert encryptor.decrypt(response.json["access_token"]) == "test-access-token"

        notion_connection = db_session.query(NotionConnection).filter_by(user_id=user_id).first()



        assert notion_connection is not None
        assert encryptor.decrypt(notion_connection.access_token) == "test-access-token"
        assert encryptor.decrypt(notion_connection.refresh_token) == "test-refresh-token"
        assert notion_connection.workspace_id == "ws1"
        assert notion_connection.expires_at is not None


@patch("app.notion.auth.service.requests.sessions.Session.post")
def test_connect_notion_no_data(mock_post, authorized_client, db_session, app, test_user):

    _, user_id = test_user

    mock_post.return_value.json.return_value = {}
    mock_post.return_value.raise_for_status = lambda: None

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)

        response = authorized_client.post("/notion/connect", json={
            "user_id": user_id,
            "code": "",
            "redirect_uri": ""
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 400
        assert "String should have at least 1 character" in response.json["detail"]


@patch("app.notion.repositories.repository.NotionAuthRepository.save_connection")
@patch("app.notion.auth.service.requests.sessions.Session.post")
def test_connect_notion_database_failure(mock_save, mock_post, authorized_client, db_session, app, test_user):

    _, user_id = test_user

    mock_post.return_value.json.return_value = {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "expires_in": 3600,
        "workspace_id": "ws1"
    }

    mock_post.return_value.raise_for_status = lambda: None

    mock_save.side_effect = DatabaseError("DB error")

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)

        response = authorized_client.post("/notion/connect", json={
            "user_id": user_id,
            "code": "test-code",
            "redirect_uri": str(HttpUrl("http://localhost"))
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 500
        assert "DB error" in response.json["detail"]


def test_map_schema_success(authorized_client, db_session, app, test_user):

    _, user_id = test_user

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)

        response = authorized_client.post("/notion/map-schema", json={
            "user_id": user_id,
            "notion_db_id": "db1",
            "title_field": "Title",
            "due_date_field": "Due",
            "duration_field": "Duration"
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200
        assert response.json["notion_db_id"] == "db1"

        field_mapping = db_session.query(FieldMapping).filter_by(user_id=user_id, notion_db_id="db1").first()

        assert field_mapping is not None
        assert field_mapping.title_field == "Title"


def test_map_schema_invalid_input(authorized_client, db_session, app, test_user):

    _, user_id = test_user

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)

        response = authorized_client.post("/notion/map-schema", json={
            "user_id": user_id,
            "notion_db_id": "",
            "title_field": "",
            "due_date_field": "",
            "duration_field": ""
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 400
        assert "notion_db_id" in response.json["detail"]


def test_map_schema_unauthorized(authorized_client, db_session, app, test_user):

    _, user_id = test_user

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)

        response = authorized_client.post("/notion/map-schema", json={
            "user_id": user_id + 1,
            "notion_db_id": "db1",
            "title_field": "Title",
            "due_date_field": "Due",
            "duration_field": "Duration"
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 403
        assert "Unauthorized access" in response.json["detail"]


@patch("app.notion.client.notion_client.NotionClient.fetch_schema")
@patch("app.notion.client.notion_client.NotionClient.fetch_rows")
@patch("app.notion.repositories.repository.NotionAuthRepository.get_connection")
@patch("app.user_preferences.preferences_store.service.PreferencesService.get_preferences")
def test_generate_candidates_success(mock_get_preferences, mock_get_connection, mock_rows, mock_schema, authorized_client, db_session, app, test_user):
    _, user_id = test_user

    # Mock UserPreferences to return PDT timezone
    mock_preferences = MagicMock()
    mock_preferences.time_zone = "America/Los_Angeles"  # PDT, UTC-7
    mock_get_preferences.return_value = mock_preferences

    # Mock schema and rows with due_date in PDT
    mock_schema.return_value = {
        "Title": {"type": "title"},
        "Due": {"type": "date"},
        "Duration": {"type": "number"}
    }

    mock_rows.return_value = [{
        "properties": {
            "Title": {"title": [{"plain_text": "Test Task"}]},
            "Due": {"date": {"start": "2023-10-10T00:00:00-07:00"}},  # PDT
            "Duration": {"number": 30}
        }
    }]

    mock_connection = NotionConnection(
        user_id=user_id,
        access_token="test-token",
        refresh_token="refresh",
        expires_at=datetime.now(timezone.utc),
        workspace_id="ws1"
    )

    mock_get_connection.return_value = mock_connection

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)
        db_session.add(mock_connection)

        field_mapping = FieldMapping(
            user_id=user_id,
            notion_db_id="db1",
            title_field="Title",
            due_date_field="Due",
            duration_field="Duration"
        )

        db_session.add(field_mapping)
        db_session.commit()

        retrieved_mapping = db_session.query(FieldMapping).filter_by(user_id=user_id, notion_db_id="db1").first()

        assert retrieved_mapping is not None
        assert retrieved_mapping.title_field == "Title"

        response = authorized_client.post("/notion/generate-candidates", json={"database_id": "db1"}, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["title"] == "Test Task"
        assert response.json[0]["due_date"] == "2023-10-10T07:00:00Z"  # UTC equivalent of PDT midnight
        assert response.json[0]["duration"] == 30
        assert response.json[0]["confidence"] > 0.5
        assert not response.json[0]["issues"]

@patch("app.notion.repositories.repository.NotionAuthRepository.get_connection")
def test_generate_candidates_no_connection(mock_get_connection, authorized_client, db_session, app, test_user):

    _, user_id = test_user
    mock_get_connection.return_value = None

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)

        response = authorized_client.post("/notion/generate-candidates", json={"database_id": "db1"}, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 404
        assert "No Notion connection" in response.json["detail"]


@patch("app.notion.client.notion_client.NotionClient.fetch_schema")
@patch("app.notion.repositories.repository.NotionAuthRepository.get_connection")
def test_generate_candidates_database_failure(mock_get_connection, mock_schema, authorized_client, db_session, app, test_user):

    _, user_id = test_user

    mock_schema.side_effect = NotionError("Notion API error")

    mock_connection = NotionConnection(
        user_id=user_id,
        access_token="test-token",
        refresh_token="refresh",
        expires_at=datetime.now(timezone.utc),
        workspace_id="ws1"
    )

    mock_get_connection.return_value = mock_connection

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)
        db_session.add(mock_connection)
        db_session.commit()

        response = authorized_client.post("/notion/generate-candidates", json={"database_id": "db1"}, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 400
        assert "Failed to fetch Notion" in response.json["detail"]


@patch("app.notion.client.notion_client.NotionClient.list_databases")
@patch("app.notion.repositories.repository.NotionAuthRepository.get_connection")
def test_list_databases_success(mock_get_connection, mock_list, authorized_client, db_session, app, test_user):

    _, user_id = test_user

    mock_list.return_value = [{"id": "db1", "title": [{"plain_text": "Test Database"}]}]

    mock_connection = NotionConnection(
        user_id=user_id,
        access_token="test-token",
        refresh_token="refresh",
        expires_at=datetime.now(timezone.utc),
        workspace_id="ws1"
    )

    mock_get_connection.return_value = mock_connection

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)
        db_session.add(mock_connection)
        db_session.commit()

        response = authorized_client.get("/notion/databases", headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["id"] == "db1"


@patch("app.notion.repositories.repository.NotionAuthRepository.get_connection")
def test_list_databases_no_connection(mock_get_connection, authorized_client, db_session, app, test_user):

    _, user_id = test_user

    mock_get_connection.return_value = None

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)

        response = authorized_client.get("/notion/databases", headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 500
        assert "No Notion connection" in response.json["detail"]


@patch("app.notion.auth.service.requests.sessions.Session.post")
@patch("app.notion.repositories.repository.NotionAuthRepository.get_connection")
def test_refresh_token_success(mock_get_connection, mock_post, authorized_client, db_session, app, test_user, encryptor):

    _, user_id = test_user

    mock_post.return_value.json.return_value = {
        "access_token": "new-token",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
        "workspace_id": "ws1"
    }

    mock_post.return_value.raise_for_status = lambda: None

    mock_connection = NotionConnection(
        user_id=user_id,
        access_token=encryptor.encrypt("old-token"),
        refresh_token=encryptor.encrypt("old-refresh"),
        expires_at=datetime.now(timezone.utc),
        workspace_id="ws1"
    )

    db_session.add(mock_connection)
    db_session.commit()

    mock_get_connection.return_value = db_session.query(NotionConnection).filter_by(user_id=user_id).first()

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)

        response = authorized_client.post("/notion/refresh-token", headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200
        assert encryptor.decrypt(response.json["access_token"]) == "new-token"

        notion_connection = db_session.query(NotionConnection).filter_by(user_id=user_id).first()

        assert encryptor.decrypt(notion_connection.access_token) == "new-token"


@patch("app.notion.repositories.repository.NotionAuthRepository.get_connection")
def test_refresh_token_no_refresh_token(mock_get_connection, authorized_client, db_session, app, test_user):

    _, user_id = test_user

    mock_connection = NotionConnection(
        user_id=user_id,
        access_token="test-token",
        refresh_token=None,
        expires_at=datetime.now(timezone.utc),
        workspace_id="ws1"
    )

    mock_get_connection.return_value = mock_connection

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)
        db_session.add(mock_connection)
        db_session.commit()

        response = authorized_client.post("/notion/refresh-token", headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 400
        assert "Token refresh failed" in response.json["detail"]


@patch("app.notion.client.notion_client.NotionClient.fetch_schema")
@patch("app.notion.auth.service.NotionAuthService.get_connection")
def test_preview_mapping_success(mock_get_connection, mock_schema, authorized_client, db_session, app, test_user):

    _, user_id = test_user

    mock_schema.return_value = {
        "Title": {"type": "title"},
        "Due": {"type": "date"},
        "Duration": {"type": "number"}
    }

    mock_connection = NotionConnection(
        user_id=user_id,
        access_token="test-token",
        refresh_token="refresh",
        expires_at=datetime.now(timezone.utc),
        workspace_id="ws1"
    )

    mock_get_connection.return_value = mock_connection

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.get(User, user_id)
        db_session.add(mock_connection)
        db_session.commit()

        response = authorized_client.post("/notion/preview-mapping", json={"database_id": "db1"}, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200
        assert len(response.json) > 0
        assert any(m["matched_concept"] == "due_date" for m in response.json)