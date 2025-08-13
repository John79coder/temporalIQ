# tests/scheduling/test_services.py (updated to mock repo directly)

from datetime import datetime, timezone
from unittest.mock import patch, Mock

import pytest

from app.features.models.entities import UserAISettings
from app.icloud.models.schemas import TimeBlock as ICloudTimeBlock, TimeBlock
from app.notion.models.entities import TaskCandidate
from app.scheduling.models.entities import Task
from app.scheduling.services.free_time_finder import FreeTimeFinder
from app.scheduling.services.task_prioritizer import TaskPrioritizer
from app.scheduling.services.time_block_generator import TimeBlockGenerator
from app.user_preferences.models.entities import UserPreferences


@pytest.fixture
def event_service():
    return Mock()


@pytest.fixture
def task_prioritizer(caching_service, features_service, preferences_service, ai_data_service, logging_service):
    return TaskPrioritizer(caching_service, features_service, preferences_service, ai_data_service, logging_service)


@pytest.fixture
def time_block_generator(caching_service, task_prioritizer, features_service, ai_data_service, logging_service):
    return TimeBlockGenerator(caching_service, None, task_prioritizer, features_service, ai_data_service,
                              logging_service)


@pytest.fixture
def free_time_finder(caching_service, event_service, features_service, preferences_service, ai_data_service,
                     logging_service, time_block_generator):
    ftf = FreeTimeFinder(caching_service, event_service, features_service, preferences_service, ai_data_service,
                         logging_service, time_block_generator)
    time_block_generator.free_time_finder = ftf
    return ftf


@patch("app.notion.repositories.repository.TaskCandidateRepository.get_candidates")
@patch("app.scheduling.services.free_time_finder.FreeTimeFinder.find_free_slots")
@patch("app.scheduling.services.task_prioritizer.TaskPrioritizer.prioritize_tasks")
def test_time_block_generator_generate(mock_prioritize_tasks, mock_find_free_slots, mock_get_candidates,
                                       time_block_generator, free_time_finder, task_prioritizer):
    mock_database_session = Mock()

    mock_find_free_slots.return_value = [
        ICloudTimeBlock(start=datetime(2025, 7, 12, 9, 0, tzinfo=timezone.utc),
                        end=datetime(2025, 7, 12, 9, 30, tzinfo=timezone.utc))
    ]

    mock_get_candidates.return_value = [
        TaskCandidate(user_id=1, notion_db_id="db1", title="Test Task", duration=30, confidence=0.9)
    ]

    mock_prioritize_tasks.return_value = [
        Task(id=1, user_id=1, notion_db_id="db1", title="Test Task", duration=30)
    ]

    with patch('app.features.services.service.FeaturesService.get_settings') as mock_get_features_settings:
        mock_get_features_settings.return_value = UserAISettings(user_id=1)

        with patch.object(time_block_generator, '_log_urgency_event', return_value=None) as mock_log_urgency:
            blocks = time_block_generator.generate_time_blocks(1, mock_database_session, "db1", "cal1",
                                                               datetime(2025, 7, 12), datetime(2025, 7, 12), "09:00",
                                                               "17:00")

    assert len(blocks) == 1
    assert blocks[0].task_id == 1


def test_free_time_finder_find_slots(free_time_finder, caching_service, event_service):
    db = Mock()
    event_service.fetch_user_events.return_value = []
    start_date = datetime(2025, 7, 12, tzinfo=timezone.utc)
    end_date = datetime(2025, 7, 12, tzinfo=timezone.utc)
    # Instance patch
    with patch.object(free_time_finder.features_service, 'get_settings') as mock_get_settings, \
            patch.object(free_time_finder.preferences_service, 'get_preferences') as mock_get_preferences, \
            patch.object(free_time_finder.ai_data_service, 'log_event') as mock_log_event, \
            patch.object(free_time_finder, '_log_duration_event') as mock_log_duration:
        mock_get_settings.return_value = UserAISettings(
            user_id=1,
            duration_learning_scope='off',
            urgency_learning_scope='off'  # ← ADD THIS
        )

        mock_get_preferences.return_value = UserPreferences(user_id=1, time_zone="UTC", work_hours=8.0,
                                                            block_size_minutes=30)
        mock_log_duration.return_value = None
        mock_log_event.return_value = None  # Mock log_event to avoid db.add on Mock db
        slots = free_time_finder.find_free_slots(1, db, "cal1", start_date, end_date, "09:00", "17:00")
    assert isinstance(slots, list)
    assert len(slots) > 0
    assert isinstance(slots[0], TimeBlock)
    assert slots[0].start == datetime(2025, 7, 12, 9, 0, tzinfo=timezone.utc)
    assert slots[0].end == datetime(2025, 7, 12, 9, 30, tzinfo=timezone.utc)


def test_task_prioritizer_prioritize(task_prioritizer):
    tasks = [
        Task(id=1, user_id=1, notion_db_id="db1", title="Task 2", priority=None),
        Task(id=2, user_id=1, notion_db_id="db1", title="Task 1", priority="low"),
        Task(id=3, user_id=1, notion_db_id="db1", title="Task 2", priority="high"),
        Task(id=4, user_id=1, notion_db_id="db1", title="Task 2", priority="medium")
    ]

    mock_database_session = Mock()
    with patch('app.features.services.service.FeaturesService.get_settings') as mock_get_settings:
        mock_get_settings.return_value = UserAISettings(user_id=1, slot_ranking_learning_scope='off')
        prioritized_tasks = task_prioritizer.prioritize_tasks(tasks, mock_database_session)

    assert len(prioritized_tasks) == 4
    assert prioritized_tasks[0].id == 3
