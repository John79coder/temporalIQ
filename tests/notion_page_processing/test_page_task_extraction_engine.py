import pytest
from unittest.mock import MagicMock, patch

from app.features.models.entities import UserAISettings
from app.features.services.service import FeaturesService
from app.notion.smart_mapping.notion_page_engine import NotionPageEngine, BlockSection
from app.notion.smart_mapping.models import TaskCandidateData

@pytest.fixture
def mock_features_service():
    mock = MagicMock()
    mock.get_settings.return_value = MagicMock(use_ai_page_extraction=True)
    return mock

@pytest.fixture
def page_engine(mock_features_service):
    engine = NotionPageEngine(MagicMock(), mock_features_service, MagicMock())
    engine.sectionizer = MagicMock()
    engine.aggregator = MagicMock()
    return engine

@patch("app.notion.smart_mapping.notion_page_engine.current_app")
def test_generate_candidates_from_page_blocks(mock_current_app, page_engine, mock_features_service, db_session):
    section = BlockSection([
        {"type": "paragraph", "text": [{"plain_text": "Finish quarterly report by Friday."}]}
    ])
    page_engine.sectionizer.segment.return_value = [section]

    page_engine.aggregator.aggregate.return_value = [
        TaskCandidateData(
            user_id=1,
            notion_db_id="p123",
            title="Quarterly Report",
            confidence=0.85,
            issues=[],
            due_date=None,
            duration=60
        )
    ]

    mock_settings = MagicMock()
    mock_settings.use_ai_page_extraction = True
    mock_features_service.get_settings.return_value = mock_settings

    candidates = page_engine.generate_candidates("p123", [{"type": "paragraph", "text": [{"plain_text": "Finish quarterly report by Friday."}]}], db_session, "1")
    assert len(candidates) == 1
    assert candidates[0].title == "Quarterly Report"
    assert candidates[0].duration == 60
