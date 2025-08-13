# tests/api/test_api_schema.py
import datetime
from unittest.mock import Mock, patch

from app.notion.models.entities import NotionConnection, FieldMapping
from app.utils.time_zone import TimeZone


def test_api_generate_candidates_response_schema(authorized_client, db_session, app, test_user):
    with app.app_context():
        notion_connection = NotionConnection(user_id=test_user[1], access_token="test",
                                             expires_at=TimeZone.utc_now() + datetime.timedelta(hours=1),
                                             workspace_id="workspace_01")
        field_mapping = FieldMapping(user_id=test_user[1], notion_db_id="db1", title_field="Title")

        db_session.add_all([notion_connection, field_mapping])
        db_session.commit()

    schema = {"Title": {"type": "title"}}
    rows = [{"properties": {"Title": {"title": [{"plain_text": "Task"}]}}}]

    with patch.multiple(
            "app.notion.client.notion_client.NotionClient",
            fetch_schema=Mock(return_value=schema),
            fetch_rows=Mock(return_value=rows)):
        response = authorized_client.post(
            "/notion/generate-candidates",
            json={"database_id": "db1"},
            headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200

        candidate = response.json[0]

        assert set(candidate.keys()) >= {"title", "due_date", "duration", "confidence", "issues", "priority", "status",
                                         "tags", "created_at"}


def test_api_input_validation_bounds(authorized_client, test_user):
    response = authorized_client.post("/user/preferences", json={"user_id": test_user[1], "block_size_minutes": 1441},
                                      headers={"X-CSRF-Token": authorized_client.csrf_token})
    assert response.status_code == 400
    assert "exceed" in response.json["detail"]


def test_api_response_type_annotations_match(app):
    from inspect import signature
    from app.notion.routes.api import generate
    sig = signature(generate)
    from flask import Response
    assert sig.return_annotation == Response


def test_missing_required_fields_error_response(authorized_client):
    response = authorized_client.post("/notion/map-schema", json={},
                                      headers={"X-CSRF-Token": authorized_client.csrf_token})
    assert response.status_code in (400, 422)
    assert "validation" in response.json["detail"].lower()


def test_openapi_schema_validation(app):
    pass
