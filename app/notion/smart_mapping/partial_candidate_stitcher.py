from collections import defaultdict
from typing import List

from requests.sessions import Session

from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.models import TaskCandidateData
from app.notion.smart_mapping.sectionizer import BlockSection
from app.user_preferences.preferences_store.service import PreferencesService
from app.utils.time_zone import TimeZone


class PageAggregator:
    def __init__(self, preferences_service: PreferencesService):
        self.preferences_service = preferences_service

    def aggregate(self, partials: List[PartialCandidate], user_id: int, page_id: str, db: Session,
                  sections: List[BlockSection], force_single_task: bool) -> List[TaskCandidateData]:
        stitched: List[TaskCandidateData] = []
        buffer: List[PartialCandidate] = []

        def flush_buffer():
            if buffer:
                stitched.append(self.merge_group(buffer, user_id, page_id, db))

        for curr in partials:
            if not buffer:
                buffer.append(curr)
                continue
            prev = buffer[-1]
            if self.is_mergeable(prev, curr):
                buffer.append(curr)
            else:
                flush_buffer()
                buffer = [curr]

        flush_buffer()

        # New: Merge candidates if user toggled single-task or page inferred as single-task
        if force_single_task or all(s.is_single_task for s in sections):
            return self.merge_candidates(stitched)

        return stitched

    def is_mergeable(self, prev: PartialCandidate, curr: PartialCandidate) -> bool:
        return (
                self.no_conflicting_fields(prev, curr) and
                self.is_adjacent(prev, curr)
        )

    def is_adjacent(self, a: PartialCandidate, b: PartialCandidate) -> bool:
        """
        Determine if two PartialCandidates are adjacent:
        - Either in the same block with sequential span indices.
        - Or in sequential blocks with span_index reset.
        - Or adjacent in extraction order as a fallback.
        """
        if a.block_index is not None and b.block_index is not None:
            if a.block_index == b.block_index:
                if a.span_index is not None and b.span_index is not None:
                    return b.span_index == a.span_index + 1
                return True  # same block, span index unknown — assume adjacency
            elif b.block_index == a.block_index + 1:
                return True  # consecutive blocks
        elif a.extraction_order is not None and b.extraction_order is not None:
            return b.extraction_order == a.extraction_order + 1

        return False  # not adjacent by any known metric

    def no_conflicting_fields(self, a: PartialCandidate, b: PartialCandidate) -> bool:
        """Ensure no overlapping fields with different values."""
        for field in ['title', 'due_date', 'duration', 'priority', 'status', 'tags']:
            a_val, b_val = getattr(a, field, None), getattr(b, field, None)
            if a_val and b_val and a_val != b_val:
                return False
        return True

    def merge_group(self, partial_candidates: List[PartialCandidate], user_id: int, page_id: str,
                    db: Session) -> TaskCandidateData:

        task_candidate = TaskCandidateData(
            user_id=user_id,
            notion_db_id="",
            page_id=page_id,
            title="Untitled",
            confidence=0.0,
            issues=[],
            due_date=None,
            duration=None
        )

        max_conf = 0.0
        tag_set = set()

        for partial_candidate in partial_candidates:

            if partial_candidate.title: task_candidate.title = partial_candidate.title

            # we're going to need the time zone from the user preferences.

            if partial_candidate.due_date:
                user_preferences = self.preferences_service.get_preferences(db, user_id)
                time_zone = user_preferences.time_zone
                task_candidate.due_date = TimeZone.to_utc(partial_candidate.due_date, time_zone)

            if partial_candidate.duration: task_candidate.duration = partial_candidate.duration
            if partial_candidate.priority: task_candidate.priority = partial_candidate.priority
            if partial_candidate.status: task_candidate.status = partial_candidate.status
            if partial_candidate.tags: tag_set.update(partial_candidate.tags)
            max_conf = max(max_conf, partial_candidate.confidence)

        task_candidate.tags = list(tag_set)
        task_candidate.confidence = max_conf or 0.5

        return task_candidate

    def merge_candidates(self, candidates: List[TaskCandidateData]) -> List[TaskCandidateData]:
        if not candidates:
            return []

        # Check for non-overlapping attributes (no conflicts across fields)
        field_values = defaultdict(set)  # Track unique non-None values per field
        has_conflict = False
        issues = set()  # Collect potential conflict issues

        for cand in candidates:
            for field in ['title', 'due_date', 'duration', 'priority', 'status']:
                value = getattr(cand, field, None)
                if value is not None:
                    if field_values[field] and value not in field_values[field]:
                        has_conflict = True
                        issues.add(
                            f"Conflict in {field}: multiple values found (e.g., {value} vs. {next(iter(field_values[field]))})")
                    field_values[field].add(value)
            # For lists like tags/issues, union later; no conflict check needed

        if has_conflict:
            # Flag conflicts but don't merge; return originals with added issues
            for cand in candidates:
                cand.issues.extend(list(issues))
            return candidates

        # No conflicts: Merge into one coherent task
        merged = TaskCandidateData(
            user_id=candidates[0].user_id,
            notion_db_id=None,
            page_id=candidates[0].page_id,
            source_block_ids=list(set(id for c in candidates for id in (c.source_block_ids or []))),
            verified=False,
            title="Untitled",
            confidence=0.5,
            issues=[],
            due_date=None,
            duration=None,
            priority=None,
            status=None,
            tags=[],
            alternatives={}
        )
        merged.created_at = TimeZone.utc_now()

        max_conf = 0.0
        tag_set = set()
        issue_set = set()
        alternatives = {}

        for cand in candidates:
            if cand.title and cand.title != "Untitled":
                merged.title = cand.title  # Prefer non-default; last wins, but no conflict, so at most one
            if cand.due_date:
                merged.due_date = cand.due_date  # At most one due to no-overlap check
            if cand.duration:
                merged.duration = cand.duration
            if cand.priority:
                merged.priority = cand.priority
            if cand.status:
                merged.status = cand.status
            if cand.tags:
                tag_set.update(cand.tags)
            if cand.issues:
                issue_set.update(cand.issues)
            if cand.alternatives:
                alternatives.update(cand.alternatives)
            max_conf = max(max_conf, cand.confidence)

        merged.tags = list(tag_set)
        merged.issues = list(issue_set)
        merged.alternatives = alternatives
        merged.confidence = max_conf or 0.5

        return [merged]
