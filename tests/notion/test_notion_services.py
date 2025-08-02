# tests/notion/test_notion_services.py
from requests.exceptions import Timeout
from app.utils.exceptions import NotionError
from datetime import timezone, datetime
import pytest
from unittest.mock import patch
from flask import g
from app.notion.auth.service import NotionAuthService
from app.notion.mapping_storage.service import MappingService
from app.notion.mapping_storage.repository import MappingRepository
from app.notion.smart_mapping.engine import MappingEngine
from app.notion.smart_mapping.schema_parser import SchemaParser
from app.notion.smart_mapping.field_detector_aggregator import FieldDetectorAggregator
from app.notion.models.entities import NotionConnection, FieldMapping
from app.notion.models.schemas import NotionTokenIn, FieldMappingIn
from app.utils.exceptions import DataValidationError
from app.notion.repositories.repository import NotionAuthRepository
from app.notion.smart_mapping.detector_registry import DetectorRegistry

from pydantic import HttpUrl


@patch("app.notion.auth.service.requests.sessions.Session.post")
def test_notion_auth_service__store_token(mock_post, db_session, app, caching_service, test_user, encryptor):

    user, _ = test_user

    mock_post.return_value.json.return_value = {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "expires_in": 3600,
        "workspace_id": "ws1"
    }

    mock_post.return_value.raise_for_status = lambda: None

    with app.app_context():

        service = NotionAuthService(NotionAuthRepository(), caching_service, encryptor)

        notion_token_in = NotionTokenIn(
            user_id=user.id,
            code="test-code",
            redirect_uri=HttpUrl("http://localhost")
        )

        notion_connection = service.store_access_token(db_session, notion_token_in)

        assert encryptor.decrypt(notion_connection.access_token) == "test-access-token"
        assert notion_connection.workspace_id == "ws1"

        retrieved_notion_connection = db_session.query(NotionConnection).filter_by(user_id=user.id).first()

        assert retrieved_notion_connection.access_token is not None
        assert retrieved_notion_connection.workspace_id is not None


def test_mapping_service__store_mapping(db_session, app, test_user):

    user, _ = test_user

    with app.app_context():

        mapping_service = MappingService(MappingRepository())

        field_mapping_in = FieldMappingIn(
            user_id=user.id,
            notion_db_id="db1",
            title_field="Title",
            due_date_field="Due",
            duration_field="Duration"
        )

        mapping_service.store_mapping(db_session, field_mapping_in)

        retrieved_mapping = db_session.query(FieldMapping).filter_by(user_id=user.id).first()

        assert retrieved_mapping.notion_db_id == "db1"
        assert retrieved_mapping.title_field == "Title"


@patch("app.notion.client.notion_client.NotionClient.fetch_schema")
@patch("app.notion.client.notion_client.NotionClient.fetch_rows")
def test_mapping_engine__generate_candidates(mock_rows, mock_schema, db_session, app, caching_service, user_preference_service, test_user, mapping_engine):

    user, _ = test_user

    with app.app_context():

        g.db = db_session

        db_session.add(NotionConnection(user_id=user.id, access_token="test-token", refresh_token="refresh", expires_at=datetime.now(timezone.utc), workspace_id="ws1"))

        db_session.add(FieldMapping(
            user_id=user.id,
            notion_db_id="db1",
            title_field="Title",
            due_date_field="Due",
            duration_field="Duration"
        ))
        db_session.commit()

        mock_schema.return_value = {
            "Title": {"type": "title"},
            "Due": {"type": "date"},
            "Duration": {"type": "number"}
        }

        mock_rows.return_value = [{
            "properties": {
                "Title": {"title": [{"plain_text": "Test Task"}]},
                "Due": {"date": {"start": "2023-10-10"}},
                "Duration": {"number": 30}
            }
        }]

        data = {"schema": mock_schema.return_value, "rows": mock_rows.return_value}

        task_candidates = mapping_engine.generate_candidates(data, db_session, user.id, "db1")

        assert len(task_candidates) == 1
        assert task_candidates[0].title == "Test Task"


@patch("app.notion.client.notion_client.NotionClient.fetch_schema")
def test_mapping_engine__invalid_schema(mock_schema, db_session, app, caching_service, user_preference_service, test_user, mapping_engine):

    user, _ = test_user

    with app.app_context():

        db_session.add(NotionConnection(user_id=user.id, access_token="test-token", refresh_token="refresh", expires_at=datetime.now(timezone.utc), workspace_id="ws1"))

        db_session.add(FieldMapping(
            user_id=user.id,
            notion_db_id="db1",
            title_field="Title",
            due_date_field="Due",
            duration_field="Duration"
        ))
        db_session.commit()

        mock_schema.return_value = {}

        data = {"schema": mock_schema.return_value, "rows": []}

        with pytest.raises(DataValidationError, match="Invalid schema"):
            mapping_engine.generate_candidates(data, db_session, user.id, "db1")


@patch("app.notion.auth.service.requests.Session.post")
@patch("app.notion.repositories.repository.NotionAuthRepository.save_connection")
def test_notion_api_timeout_handling(mock_save, mock_post, db_session, caching_service, encryptor):
    mock_post.side_effect = Timeout("Timeout")
    service = NotionAuthService(NotionAuthRepository(), caching_service, encryptor)
    token_data = NotionTokenIn(user_id=1, code="code", redirect_uri=HttpUrl("http://localhost"))
    with pytest.raises(NotionError, match="Failed to exchange Notion auth code"):
        service.store_access_token(db_session, token_data)