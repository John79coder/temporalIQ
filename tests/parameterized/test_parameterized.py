from datetime import datetime
from unittest.mock import Mock, patch
import pytest
from flask import g

from app.notion.models.entities import FieldMapping
from app.notion.smart_mapping.task_candidate import TaskCandidateBuilder


@pytest.mark.parametrize("format", [
    "2025-07-19T12:00:00Z", "2025-07-19", "2025-07-19T12:00:00+00:00"
])
def test_task_candidate_due_date_formats(format, db_session):
    mock_service = Mock()
    mock_prefs = Mock(time_zone="America/New_York")
    mock_service.get_preferences.side_effect = lambda db, uid: mock_prefs

    builder = TaskCandidateBuilder(mock_service)
    row = {"properties": {"Due": {"date": {"start": format}}}}
    mapping = FieldMapping(due_date_field="Due")
    candidate = builder.build_from_row(db_session, [], row, mapping, user_id=1, notion_db_id="db1")

    assert isinstance(candidate.due_date, datetime)
