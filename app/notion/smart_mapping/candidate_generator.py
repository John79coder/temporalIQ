# notion/smart_mapping/candidate_generator.py
from typing import List
from sqlalchemy.orm import Session
from app.notion.smart_mapping.interfaces import ICandidateGenerator
from app.notion.smart_mapping.models import TaskCandidateData
from app.notion.smart_mapping.task_candidate import TaskCandidateBuilder
from app.notion.models.entities import FieldMapping
from app.utils.exceptions import DatabaseError, DataValidationError, wrap_external_error
from app.utils.caching import ICacheService

class CandidateGenerator(ICandidateGenerator):
    def __init__(self, caching_service: ICacheService, task_candidate_builder: TaskCandidateBuilder):
        self.caching_service = caching_service
        self.task_candidate_builder = task_candidate_builder

    def generate_candidates(self, data: dict, db: Session, user_id: int, database_id: str) -> List[TaskCandidateData]:
        """Generate task candidates from schema and rows."""
        schema = data["schema"]
        rows = data.get("rows", [])
        if not schema:
            raise DataValidationError("Invalid schema")
        if len(rows) > 100:
            rows = rows[:100]
        cache_key = f"notion:mapping:{user_id}:{database_id}"
        mapping = self.caching_service.get(cache_key)

        if mapping: mapping = FieldMapping(**mapping)

        if not mapping:
            try:
                mapping = db.query(FieldMapping).filter_by(user_id=user_id, notion_db_id=database_id).first()
            except Exception as e:
                raise wrap_external_error(e, DatabaseError, "Failed to retrieve field mapping")
            if mapping:
                self.caching_service.set(cache_key, mapping.__dict__, timeout=604800)
            else:
                raise DataValidationError(f"No field mapping found for user_id={user_id} and notion_db_id={database_id}")
        candidates = []
        for row in rows:
            candidate = self.task_candidate_builder.build_from_row(db,[], row, mapping, user_id=user_id, notion_db_id=database_id)
            candidates.append(candidate)
        return candidates