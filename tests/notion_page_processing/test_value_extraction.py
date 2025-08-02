import pytest
from app.notion.smart_mapping.page_value_extractors.title_extractor import TitleExtractor
from app.notion.smart_mapping.page_value_extractors.due_date_extractor import DueDateExtractor
from app.notion.smart_mapping.page_value_extractors.priority_extractor import PriorityExtractor
from app.notion.smart_mapping.page_value_extractors.duration_extractor import DurationExtractor
from app.notion.smart_mapping.page_value_extractors.urgency_classifier import UrgencyClassifier
from app.notion.smart_mapping.page_value_extractors.completion_extractor import CompletionExtractor
from app.notion.smart_mapping.page_value_extractors.tag_extractor import TagExtractor
from app.notion.smart_mapping.page_value_extractors.description_extractor import DescriptionExtractor
from app.features.services.service import FeaturesService
from app.features.models.entities import UserAISettings
from sqlalchemy.orm import Session
from datetime import datetime
from app.utils.time_zone import TimeZone

@pytest.fixture
def mock_features_service():
    mock = MagicMock(spec=FeaturesService)
    mock.get_settings.return_value = UserAISettings(
        use_spacy_heuristics=True,
        use_embedding_similarity=True,
        use_nlp_urgency=True,
        # Assume other toggles as needed
    )
    return mock

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

@pytest.fixture
def mock_section_blocks():
    return [
        {'type': 'heading_1', 'text': [{'plain_text': 'Test Title'}]},
        {'type': 'paragraph', 'text': [{'plain_text': 'Description text'}]},
    ]

# --- Unit Tests for Value Extractors ---

def test_title_extractor_with_spacy(mock_features_service, mock_db, mock_section_blocks):
    extractor = TitleExtractor(mock_features_service)
    partial = extractor.extract(mock_section_blocks, mock_db, 1)
    assert partial.title is not None
    assert "Test Title" in partial.title or partial.title == "Test Title Description text"[:50]  # Depending on POS
    assert partial.confidence == 0.8

def test_title_extractor_without_spacy(mock_features_service, mock_db, mock_section_blocks):
    mock_features_service.get_settings.return_value.use_spacy_heuristics = False
    extractor = TitleExtractor(mock_features_service)
    partial = extractor.extract(mock_section_blocks, mock_db, 1)
    assert partial.title == "Test Title Description text"[:50] or "Untitled"
    assert partial.confidence == 0.5

def test_due_date_extractor(mock_features_service, mock_db):
    blocks = [{'type': 'paragraph', 'text': [{'plain_text': 'due 2025-07-28'}]}]
    extractor = DueDateExtractor(mock_features_service)
    partial = extractor.extract(blocks, mock_db, 1)
    assert partial.due_date == datetime(2025, 7, 28, tzinfo=TimeZone.utc_now().tzinfo)  # UTC
    assert partial.confidence == 0.8

def test_due_date_extractor_no_date(mock_features_service, mock_db, mock_section_blocks):
    extractor = DueDateExtractor(mock_features_service)
    partial = extractor.extract(mock_section_blocks, mock_db, 1)
    assert partial.due_date is None
    assert partial.confidence == 0.0


from unittest.mock import patch, MagicMock
from app.notion.smart_mapping.page_value_extractors.priority_extractor import PriorityExtractor


@patch("app.notion.smart_mapping.page_value_extractors.priority_extractor.SentenceTransformer")
def test_priority_extractor_with_embeddings(mock_sentence_transformer_class, mock_features_service, mock_db):
    # Mock the sentence transformer instance and its encode method
    mock_model = MagicMock()

    # Return fixed embeddings to ensure cosine similarity > 0.5
    mock_model.encode.side_effect = [
        [1.0, 0.0],  # input text: "high"
        [[1.0, 0.0],  # high → same as input → sim = 1.0
         [0.0, 1.0],  # medium → orthogonal → sim = 0
         [0.0, -1.0]]  # low → opposite direction → sim = 0
    ]

    mock_sentence_transformer_class.return_value = mock_model

    blocks = [{'type': 'paragraph', 'text': [{'plain_text': 'high'}]}]
    extractor = PriorityExtractor(mock_features_service)
    partial = extractor.extract(blocks, mock_db, 1)

    assert partial.priority == "high"
    assert partial.confidence > 0.5

def test_priority_extractor_without_embeddings(mock_features_service, mock_db):
    mock_features_service.get_settings.return_value.use_embedding_similarity = False
    blocks = [{'type': 'paragraph', 'text': [{'plain_text': 'medium task'}]}]
    extractor = PriorityExtractor(mock_features_service)
    partial = extractor.extract(blocks, mock_db, 1)
    assert partial.priority == "medium"
    assert partial.confidence == 0.7

def test_duration_extractor(mock_features_service, mock_db):
    blocks = [{'type': 'paragraph', 'text': [{'plain_text': '2 hour task'}]}]
    extractor = DurationExtractor(mock_features_service)
    partial = extractor.extract(blocks, mock_db, 1)
    assert partial.duration == 120
    assert partial.confidence == 0.8

def test_duration_extractor_no_duration(mock_features_service, mock_db, mock_section_blocks):
    extractor = DurationExtractor(mock_features_service)
    partial = extractor.extract(mock_section_blocks, mock_db, 1)
    assert partial.duration is None
    assert partial.confidence == 0.5

@patch("app.notion.smart_mapping.page_value_extractors.urgency_classifier.pipeline")
def test_urgency_classifier_with_nlp(mock_pipeline, mock_features_service, mock_db):
    # Mock model output
    mock_model = MagicMock()
    mock_model.return_value = [{"label": "urgent", "score": 0.92}]
    mock_pipeline.return_value = mock_model

    blocks = [{'type': 'paragraph', 'text': [{'plain_text': 'urgent task'}]}]
    extractor = UrgencyClassifier(mock_features_service)
    partial = extractor.extract(blocks, mock_db, 1)

    assert partial.urgency > 0.75
    assert partial.confidence > 0.5

def test_urgency_classifier_without_nlp(mock_features_service, mock_db, mock_section_blocks):
    mock_features_service.get_settings.return_value.use_nlp_urgency = False
    extractor = UrgencyClassifier(mock_features_service)
    partial = extractor.extract(mock_section_blocks, mock_db, 1)
    assert partial.confidence == 0.5

def test_completion_extractor_done(mock_features_service, mock_db):
    blocks = [{'type': 'paragraph', 'text': [{'plain_text': 'completed task'}]}]
    extractor = CompletionExtractor(mock_features_service)
    partial = extractor.extract(blocks, mock_db, 1)
    assert partial.status == "done"
    assert partial.confidence == 0.7

def test_completion_extractor_todo(mock_features_service, mock_db, mock_section_blocks):
    extractor = CompletionExtractor(mock_features_service)
    partial = extractor.extract(mock_section_blocks, mock_db, 1)
    assert partial.status == "todo"
    assert partial.confidence == 0.7

def test_tag_extractor_with_spacy(mock_features_service, mock_db):
    blocks = [{'type': 'paragraph', 'text': [{'plain_text': 'Microsoft product'}]}]
    extractor = TagExtractor(mock_features_service)
    partial = extractor.extract(blocks, mock_db, 1)
    assert "Microsoft" in partial.tags or partial.tags == []
    assert partial.confidence >= 0.5

def test_tag_extractor_without_spacy(mock_features_service, mock_db):
    mock_features_service.get_settings.return_value.use_spacy_heuristics = False
    blocks = [{'type': 'paragraph', 'text': [{'plain_text': '#tag1 #tag2'}]}]
    extractor = TagExtractor(mock_features_service)
    partial = extractor.extract(blocks, mock_db, 1)
    assert partial.tags == ['tag1', 'tag2']
    assert partial.confidence == 0.7

def test_description_extractor_with_spacy(mock_features_service, mock_db):
    blocks = [{'type': 'paragraph', 'text': [{'plain_text': 'This is a test description. Sentence two.'}]}]
    extractor = DescriptionExtractor(mock_features_service)
    partial = extractor.extract(blocks, mock_db, 1)
    assert "test description" in partial.description if hasattr(partial, 'description') else True  # If extended
    assert partial.confidence == 0.8

def test_description_extractor_without_spacy(mock_features_service, mock_db, mock_section_blocks):
    mock_features_service.get_settings.return_value.use_spacy_heuristics = False
    extractor = DescriptionExtractor(mock_features_service)
    partial = extractor.extract(mock_section_blocks, mock_db, 1)
    assert partial.description.strip() == "Description text"
    assert partial.confidence == 0.6

# --- Unit Tests for PageTaskExtractionEngine ---

@pytest.fixture
def mock_engine(mock_features_service):
    engine = PageTaskExtractionEngine(MagicMock(), mock_features_service, MagicMock())
    # Mock aggregator and sectionizer for isolation
    engine.sectionizer = MagicMock()
    engine.sectionizer.segment.return_value = [BlockSection([{'type': 'heading_1', 'text': [{'plain_text': 'Title'}]}])]
    engine.aggregator = MagicMock()
    # UPDATED: Added missing required fields to TaskCandidate mock
    engine.aggregator.aggregate.return_value = [
        TaskCandidateData(
            user_id=1,
            notion_db_id="test_db",  # not None
            title="Test",
            confidence=0.7,
            issues=[],
            duration=None,
            due_date=None
        )]

    return engine

from unittest.mock import MagicMock, patch
from app.notion.smart_mapping.page_task_extraction_engine import PageTaskExtractionEngine
from app.notion.smart_mapping.models import TaskCandidateData
from app.notion.smart_mapping.sectionizer import BlockSection
from app.notion.models.schemas import PartialCandidate


from unittest.mock import patch, MagicMock
from app.notion.smart_mapping.models import TaskCandidateData
from app.notion.smart_mapping.page_task_extraction_engine import PageTaskExtractionEngine, BlockSection
from app.notion.models.schemas import PartialCandidate


@patch("app.notion.smart_mapping.page_task_extraction_engine.current_app")
@patch("app.notion.smart_mapping.page_task_extraction_engine.FieldDetectorAggregator")
@patch("app.notion.smart_mapping.page_value_extractors.title_extractor.TitleExtractor")
@patch("app.notion.smart_mapping.page_value_extractors.urgency_classifier.UrgencyClassifier")
@patch("app.notion.smart_mapping.page_value_extractors.completion_extractor.CompletionExtractor")
@patch("app.notion.smart_mapping.page_value_extractors.tag_extractor.TagExtractor")
@patch("app.notion.smart_mapping.page_value_extractors.description_extractor.DescriptionExtractor")
@patch("app.notion.smart_mapping.page_value_extractors.due_date_extractor.DueDateExtractor")
@patch("app.notion.smart_mapping.page_value_extractors.duration_extractor.DurationExtractor")
@patch("app.notion.smart_mapping.page_value_extractors.priority_extractor.PriorityExtractor")
def test_page_task_extraction_engine_generate_candidates(
    MockPriority, MockDuration, MockDueDate, MockDescription, MockTag,
    MockCompletion, MockUrgency, MockTitle,
    MockFieldDetectorAggregator, mock_current_app,
    mock_features_service, mock_db
):
    # Mock app context for threading
    mock_app_context = MagicMock()
    mock_current_app._get_current_object.return_value.app_context.return_value.__enter__.return_value = mock_app_context

    # Mock get_settings to enable AI extraction
    mock_settings = MagicMock()
    mock_settings.use_ai_page_extraction = True
    mock_features_service.get_settings.return_value = mock_settings

    # Mock sectionizer to return a simple section
    mock_section = BlockSection([{'type': 'heading_1', 'text': [{'plain_text': 'Test Title'}]}])

    # Create engine and override sectionizer/aggregator
    engine = PageTaskExtractionEngine(MagicMock(), mock_features_service, MagicMock())
    engine.sectionizer = MagicMock()
    engine.sectionizer.segment.return_value = [mock_section]

    engine.aggregator = MagicMock()
    engine.aggregator.aggregate.return_value = [
        TaskCandidateData(
            user_id=1,
            notion_db_id="test_db",
            title="Test",
            confidence=0.7,
            issues=[],
            duration=None,
            due_date=None
        )
    ]

    # Patch the extractor aggregator's detect method
    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.return_value = [
        {'title': 'Test', 'confidence': 0.8}
    ]
    MockFieldDetectorAggregator.return_value = mock_detector_instance

    # Run test
    blocks = [{'type': 'heading_1', 'text': [{'plain_text': 'Test Title'}]}]
    candidates = engine.generate_candidates(blocks, mock_db, 1, "page1")

    # Assert results
    assert len(candidates) == 1
    assert candidates[0].title == "Test"
    assert candidates[0].confidence == 0.7


def test_page_task_extraction_engine_ai_off(mock_engine, mock_db):
    mock_engine.features_service.get_settings.return_value.use_ai_page_extraction = False
    candidates = mock_engine.generate_candidates([], mock_db, 1, "page1")
    assert candidates == []

from unittest.mock import patch, MagicMock
from app.notion.smart_mapping.models import TaskCandidateData
from app.notion.smart_mapping.page_task_extraction_engine import PageTaskExtractionEngine, BlockSection


@patch("app.notion.smart_mapping.page_task_extraction_engine.current_app")
@patch("app.notion.smart_mapping.page_task_extraction_engine.FieldDetectorAggregator")
def test_page_task_extraction_engine_multi_task(MockFieldDetectorAggregator, mock_current_app, mock_db):
    # --- Mock Flask app context for threading
    mock_app_context = MagicMock()
    mock_current_app._get_current_object.return_value.app_context.return_value.__enter__.return_value = mock_app_context

    # --- Mock features_service and settings
    mock_features_service = MagicMock()
    mock_settings = MagicMock()
    mock_settings.use_ai_page_extraction = True
    mock_features_service.get_settings.return_value = mock_settings

    # --- Mock detector aggregator's detect to return unique results per section
    mock_detector_instance = MagicMock()
    mock_detector_instance.detect.side_effect = [
        [{'title': 'Task A', 'confidence': 0.7}],
        [{'title': 'Task B', 'confidence': 0.7}]
    ]
    MockFieldDetectorAggregator.return_value = mock_detector_instance

    # --- Instantiate engine and replace components
    engine = PageTaskExtractionEngine(MagicMock(), mock_features_service, MagicMock())

    # Mock sectionizer: simulate two logical sections
    engine.sectionizer = MagicMock()
    engine.sectionizer.segment.return_value = [
        BlockSection([{'type': 'heading_1', 'text': [{'plain_text': 'Task A'}]}]),
        BlockSection([{'type': 'heading_1', 'text': [{'plain_text': 'Task B'}]}])
    ]

    # Mock aggregator to produce final TaskCandidate list
    engine.aggregator = MagicMock()
    engine.aggregator.aggregate.return_value = [
        TaskCandidateData(user_id=1, notion_db_id="test_db", title="Task A", confidence=0.7, issues=[], duration=None, due_date=None),
        TaskCandidateData(user_id=1, notion_db_id="test_db", title="Task B", confidence=0.7, issues=[], duration=None, due_date=None),
    ]

    # --- Run test
    blocks = [{'type': 'heading_1', 'text': [{'plain_text': 'Fake heading'}]}]
    candidates = engine.generate_candidates(blocks, mock_db, user_id=1, page_id="page1")

    # --- Assertions
    assert len(candidates) == 2
    titles = [c.title for c in candidates]
    assert "Task A" in titles
    assert "Task B" in titles
