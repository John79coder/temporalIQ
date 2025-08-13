# tests/data_driven/test_data_driven.py

import pytest

from app.notion.smart_mapping.candidate_generator import CandidateGenerator
from app.notion.smart_mapping.detector_registry import DetectorRegistry
from app.notion.smart_mapping.field_detector_aggregator import FieldDetectorAggregator
from app.notion.smart_mapping.notion_database_engine import NotionDatabaseEngine
from app.notion.smart_mapping.schema_parser import SchemaParser
from app.notion.smart_mapping.task_candidate import TaskCandidateBuilder
from config import Config


@pytest.mark.parametrize("inputs,expected", [
    ({"schema": {"Due": {"type": "date"}, "End": {"type": "date"}}}, "Due"),
])
def test_mapping_engine_conflicting_field_inputs(test_user, inputs, db_session, expected, caching_service,
                                                 user_preference_service, features_service, ai_data_service,
                                                 logging_service, preferences_service):
    user, user_id = test_user
    detector_registry = DetectorRegistry(features_service, ai_data_service, logging_service)
    detector_registry.initialize_default_detectors(),
    detector_aggregator = FieldDetectorAggregator(detector_registry)
    engine = NotionDatabaseEngine(caching_service, SchemaParser(), detector_aggregator,
                                  CandidateGenerator(caching_service, TaskCandidateBuilder(preferences_service)),
                                  features_service)
    matches = engine.preview_field_matches(inputs["schema"], db_session, user_id)
    due_matches = [m for m in matches if m.matched_concept == "due_date"]
    assert len(due_matches) > 0
    assert sorted(due_matches, key=lambda m: m.confidence, reverse=True)[0].notion_field == expected


def test_logging_to_file(app, logging_service):
    with app.app_context():
        # Debug logger state
        print(f"Logger handlers: {logging_service.logger.handlers}")
        print(f"Logger level: {logging_service.logger.getEffectiveLevel()}")
        logging_service.error("Test error message", user_id=1, extra={"test": "log"})
        log_file = Config.LOG_FILE_PATH
        print(f"Checking log file: {log_file}")
        try:
            with open(log_file, "r") as f:
                content = f.read()
                print(f"Log file content: {content}")
                assert "Test error message" in content
        except FileNotFoundError:
            print(f"Log file {log_file} not found")
            assert False, f"Log file {log_file} not found"
