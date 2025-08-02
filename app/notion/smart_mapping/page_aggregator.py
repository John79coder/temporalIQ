from typing import List
from app.notion.smart_mapping.models import TaskCandidateData
from app.notion.smart_mapping.sectionizer import BlockSection
from app.utils.time_zone import TimeZone
from app.notion.models.schemas import PartialCandidate


class Aggregator:
    def aggregate(self, partial_candidates: List['PartialCandidate'], user_id: int, page_id: str, sections: List[BlockSection]) -> \
    List[TaskCandidateData]:
        """Merge partial candidates into full TaskCandidates, inferring single/multi-task."""
        if not partial_candidates:
            return []

        # Single-task: Merge all partials into one candidate
        if all(s.is_single_task for s in sections):
            merged = TaskCandidateData(
                user_id=user_id,
                notion_db_id=None,
                page_id=page_id,
                source_block_ids=[b['id'] for s in sections for b in s.blocks if 'id' in b],
                verified=False,
                title="Untitled",
                confidence=0.5,
                issues=[]
            )
            merged.created_at = TimeZone.utc_now()
            for p in partial_candidates:
                if p.title: merged.title = p.title
                if p.due_date: merged.due_date = p.due_date
                if p.duration: merged.duration = p.duration
                if p.priority: merged.priority = p.priority
                if p.status: merged.status = p.status
                if p.tags: merged.tags = p.tags
                merged.confidence = max(merged.confidence, p.confidence)
            return [merged]

        # Multi-task: One candidate per section/partial
        candidates = []
        for i, partial in enumerate(partial_candidates):
            cand = TaskCandidateData(
                user_id=user_id,
                notion_db_id=None,
                page_id=page_id,
                source_block_ids=[b['id'] for b in sections[i].blocks if 'id' in b],
                verified=False,
                title=partial.title or "Untitled",
                due_date=partial.due_date,
                duration=partial.duration,
                priority=partial.priority,
                status=partial.status,
                tags=partial.tags or [],
                confidence=partial.confidence,
                issues=[]
            )
            cand.created_at = TimeZone.utc_now()
            candidates.append(cand)
        return candidates