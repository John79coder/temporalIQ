from unittest.mock import MagicMock, patch

import pytest

from app.notion.smart_mapping.models import TaskCandidateData
from app.notion.smart_mapping.notion_page_engine import NotionPageEngine, BlockSection


@pytest.fixture
def mock_features_service():
    mock = MagicMock()
    mock.get_settings.return_value = MagicMock(use_ai_page_extraction=True)
    return mock


@pytest.fixture
def page_engine(mock_features_service):
    engine = NotionPageEngine(MagicMock(), mock_features_service, MagicMock(), MagicMock())
    engine.sectionizer = MagicMock()
    engine.aggregator = MagicMock()
    engine.registry = MagicMock()
    return engine


@patch("app.notion.smart_mapping.notion_page_engine.current_app")
def test_generate_candidates_from_page_blocks(mock_current_app, page_engine, mock_features_service, db_session):
    section = BlockSection([
        {"type": "paragraph", "text": [{"plain_text": "Finish quarterly report by Friday."}]}
    ])
    page_engine.sectionizer.segment.return_value = [section]

    expected_candidates = [
        TaskCandidateData(
            user_id=1,
            notion_db_id=None,  # Updated: Align with page-based extraction (notion_db_id=None)
            page_id="p123",
            title="Quarterly Report",
            confidence=0.85,
            issues=[],
            due_date=None,
            duration=60
        )
    ]

    # Fix: Mock aggregate to handle all six arguments
    page_engine.aggregator.aggregate.side_effect = lambda partials, uid, pid, db, sections, force: expected_candidates

    mock_settings = MagicMock()
    mock_settings.use_ai_page_extraction = True
    mock_settings.use_sentence_splitter = True  # Ensure splitter is toggled on if needed
    mock_features_service.get_settings.return_value = mock_settings

    # Fix: Correct call with proper args
    candidates = page_engine.generate_candidates(
        blocks=[{"type": "paragraph", "text": [{"plain_text": "Finish quarterly report by Friday."}]}],
        db=db_session,
        user_id=1,
        page_id="p123",
        force_single_task=False
    )

    assert len(candidates) == 1
    assert candidates[0].title == "Quarterly Report"
    assert candidates[0].duration == 60
    assert candidates[0].confidence == 0.85
