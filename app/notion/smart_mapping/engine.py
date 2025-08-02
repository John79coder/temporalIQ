# app/notion/smart_mapping/engine.py
from app.notion.smart_mapping.models import FieldMatch, TaskCandidateData
from app.notion.smart_mapping.schema_parser import SchemaParser
from app.notion.smart_mapping.field_detector_aggregator import FieldDetectorAggregator
from app.notion.smart_mapping.candidate_generator import CandidateGenerator
from app.notion.smart_mapping.scoring.ml_model import MLModelScorer
from sqlalchemy.orm import Session
from app.utils.exceptions import DatabaseError, DataValidationError, wrap_external_error
from app.utils.caching import ICacheService
from typing import List
from app.features.services.service import FeaturesService


class MappingEngine:
    def __init__(self, caching_service: ICacheService, schema_parser: SchemaParser,
                 detector_aggregator: FieldDetectorAggregator, candidate_generator: CandidateGenerator, features_service: FeaturesService):
        self.caching_service = caching_service
        self.schema_parser = schema_parser
        self.detector_aggregator = detector_aggregator
        self.candidate_generator = candidate_generator
        self.scorer = MLModelScorer(features_service)

    def generate_candidates(self, data: dict, db: Session = None, user_id: int = None, database_id: str = None) -> List[TaskCandidateData]:
        if not user_id or not db:
            raise DataValidationError("User ID and database session are required")
        try:
            normalized = self.schema_parser.normalize(data["schema"])
            if not normalized:
                raise DataValidationError("Invalid schema")
            matches = self.detector_aggregator.detect(normalized, rows=data.get("rows", []), db=db, user_id=user_id)
            scored_matches = self.scorer.score(matches)
            candidates = self.candidate_generator.generate_candidates(data, db, user_id, database_id)
            return candidates
        except DataValidationError as e:
            raise e
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to generate candidates")

    def preview_field_matches(self, schema: dict, db: Session, user_id: int) -> List[FieldMatch]:
        cache_key = f"notion:preview:{hash(str(schema))}"
        cached_matches = self.caching_service.get(cache_key)
        if cached_matches:
            return [FieldMatch(**m) for m in cached_matches]
        normalized = self.schema_parser.normalize(schema)
        matches = self.detector_aggregator.detect(normalized, db=db, user_id=user_id)
        scored_matches = self.scorer.score(matches)
        self.caching_service.set(
            cache_key,
            [m.__dict__ for m in scored_matches],
            timeout=3600
        )
        return scored_matches