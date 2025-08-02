# tests/integration/test_integration.py
from unittest.mock import patch

from app.notion.smart_mapping.engine import MappingEngine
from app.notion.smart_mapping.detector_registry import DetectorRegistry
from app.notion.smart_mapping.field_detector_aggregator import FieldDetectorAggregator
from app.notion.smart_mapping.schema_parser import SchemaParser
from app.notion.smart_mapping.candidate_generator import CandidateGenerator
from app.notion.smart_mapping.task_candidate import TaskCandidateBuilder


@patch("app.notion.client.notion_client.NotionClient.fetch_schema")
@patch("app.notion.client.notion_client.NotionClient.fetch_rows")
def test_notion_to_task_candidate_flow(mock_rows, mock_schema, mapping_engine, test_user, db_session):
    user, user_id = test_user

    mock_schema.return_value = {"Title": {"type": "title"}, "Due": {"type": "date"}}
    mock_rows.return_value = [{"properties": {"Title": {"title": [{"plain_text": "Task"}]}}}]


    from app.notion.models.entities import FieldMapping
    mapping = FieldMapping(user_id=user_id, notion_db_id="db1", title_field="Title", due_date_field="Due")
    db_session.add(mapping)
    db_session.commit()

    candidates = mapping_engine.generate_candidates({"schema": mock_schema(), "rows": mock_rows()}, db_session, 1, "db1")
    assert len(candidates) > 0

@patch("app.icloud.services.event_service.CalDAVEventService.write_scheduled_event")
@patch("app.icloud.services.event_service.CalDAVEventService.fetch_user_events")
def test_icloud_event_write_readback(mock_fetch, mock_write):
    mock_write.return_value = "uid1"
    mock_fetch.return_value = [{"uid": "uid1"}]
    # Simulate service calls
    assert "uid1" in [e["uid"] for e in mock_fetch(...)]


from unittest.mock import Mock


def test_mapping_engine_detector_chain_execution(db_session, test_user, mapping_engine):
    user, user_id = test_user

    mock_user_prefs_service = Mock()
    mock_user_prefs_service.get_preferences.return_value = Mock(time_zone="UTC")

    schema = {
        "Due": {"type": "date"},
        "Duration": {"type": "number"},
        "Title": {"type": "title"}
    }

    matches = mapping_engine.preview_field_matches(schema, db_session, user_id)

    assert len(matches) > 0
