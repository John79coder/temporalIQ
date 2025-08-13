from typing import List

from app.features.services.ai_data_service import AIDataService
from app.features.services.service import FeaturesService
from app.notion.smart_mapping.field_detectors.field_type_heuristics import FieldTypeHeuristics
from app.notion.smart_mapping.field_detectors.keyword_matcher import KeywordMatcher
from app.notion.smart_mapping.field_detectors.learned_detector import LearnedDetector
from app.notion.smart_mapping.field_detectors.llm_detector import LLMDetector
from app.notion.smart_mapping.field_detectors.string_similarity import StringSimilarityMatcher
from app.utils.logging_service import LoggingService


class DetectorRegistry:
    def __init__(self, features_service: FeaturesService, ai_data_service: AIDataService,
                 logging_service: LoggingService):
        self.features_service = features_service
        self.ai_data_service = ai_data_service
        self.logging_service = logging_service
        self.detectors = []

    def register_detector(self, detector) -> None:
        """Register a new field detector."""
        self.detectors.append(detector)

    def get_detectors(self) -> List:
        """Return all registered detectors."""
        return self.detectors

    def initialize_default_detectors(self) -> "DetectorRegistry":
        """Initialize default detectors."""
        self.register_detector(KeywordMatcher())
        self.register_detector(StringSimilarityMatcher(self.features_service))
        self.register_detector(FieldTypeHeuristics(self.features_service))
        self.register_detector(LLMDetector(self.features_service, self.logging_service))
        self.register_detector(LearnedDetector(self.features_service, self.ai_data_service, self.logging_service))
        return self
