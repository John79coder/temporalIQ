# app/notion/mapping_storage/service.py
from typing import List

from sqlalchemy.orm import Session

from app.notion.mapping_storage.repository import MappingRepository
from app.notion.models.entities import FieldMapping, TaskCandidate
from app.notion.models.schemas import FieldMappingIn
from app.notion.repositories.repository import TaskCandidateRepository
from app.notion.smart_mapping.models import TaskCandidateData
from app.utils.exceptions import DatabaseError, wrap_external_error


class MappingService:
    def __init__(self, repo: MappingRepository):
        self.repo = repo
        self.task_candidate_repo = TaskCandidateRepository()

    def store_mapping(self, db: Session, mapping_data: FieldMappingIn) -> FieldMapping:
        mapping = FieldMapping(
            user_id=mapping_data.user_id,
            notion_db_id=mapping_data.notion_db_id,
            title_field=mapping_data.title_field,
            due_date_field=mapping_data.due_date_field,
            duration_field=mapping_data.duration_field
        )
        return self.repo.save(db, mapping)

    def get_mapping(self, db: Session, user_id: int, notion_db_id: str) -> FieldMapping | None:
        return self.repo.get_mapping(db, user_id, notion_db_id)

    def save_task_candidates(self, db: Session, candidate_data: List[TaskCandidateData]) -> list[TaskCandidate]:
        try:
            db_candidates = []
            for c in candidate_data:
                db_c = TaskCandidate(
                    user_id=c.user_id,
                    notion_db_id=c.notion_db_id,
                    title=c.title,
                    due_date=c.due_date,
                    duration=c.duration,
                    confidence=c.confidence,
                    issues=c.issues,
                    priority=c.priority,
                    status=c.status,
                    tags=c.tags,
                    alternatives=c.alternatives,
                    page_id=c.page_id if hasattr(c, 'page_id') else None,
                    source_block_ids=c.source_block_ids if hasattr(c, 'source_block_ids') else None,
                    verified=c.verified if hasattr(c, 'verified') else False
                )
                db_candidates.append(db_c)
            self.task_candidate_repo.save_candidates(db, db_candidates)
            return db_candidates
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to save task candidates")