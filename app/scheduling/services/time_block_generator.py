# app/scheduling/services/time_block_generator.py
import os
import re
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from flask import g, current_app
from huggingface_hub.errors import EntryNotFoundError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from transformers import pipeline

from app.features.models.entities import AITrainingEvent, UserAISettings
from app.features.models.schemas import UrgencyFeedbackInput, UrgencyFeedbackLabel
from app.features.services.ai_data_service import AIDataService
from app.features.services.service import FeaturesService
from app.notion.repositories.repository import TaskCandidateRepository
from app.notion.smart_mapping.models import TaskCandidateData
from app.scheduling.models.entities import Task, TimeBlock
from app.scheduling.models.policies import SchedulingPolicy
from app.scheduling.services.free_time_finder import IFreeTimeFinder
from app.scheduling.services.interfaces import ITimeBlockGenerator
from app.scheduling.services.task_prioritizer import ITaskPrioritizer
from app.utils.caching import ICacheService
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.logging_service import LoggingService


class TimeBlockGenerator(ITimeBlockGenerator):
    def __init__(self, caching_service: ICacheService, free_time_finder: IFreeTimeFinder,
                 task_prioritizer: ITaskPrioritizer, features_service: FeaturesService, ai_data_service: AIDataService,
                 logging_service: LoggingService):
        self.caching_service = caching_service
        self.free_time_finder = free_time_finder
        self.task_prioritizer = task_prioritizer
        self.features_service = features_service
        self.ai_data_service = ai_data_service
        self.logging_service = logging_service
        self.task_candidate_repo = TaskCandidateRepository()
        self.nlp = None

    def _check_nlp_enabled(self, user_id: int) -> bool:
        """Check if NLP urgency detection is enabled for the user."""
        settings = self.features_service.get_settings(g.db, user_id) if g.get('db') else None
        return settings and settings.use_nlp_urgency and settings.urgency_learning_scope != 'off'

    def get_urgency_score(self, title: str, user_id: int) -> float:
        """Get urgency score for a task title."""
        return self._analyze_task_urgency(title, user_id) if self._check_nlp_enabled(
            user_id) else self._heuristic_urgency(title)

    def generate_time_blocks(
            self,
            user_id: int,
            db: Session,
            notion_db_id: str,
            calendar_id: str,
            start_date: datetime,
            end_date: datetime,
            earliest_time: str,
            latest_time: str
    ) -> List[TimeBlock]:
        """Generate time blocks for tasks in the given calendar and date range."""
        cache_key = f"scheduling:blocks:{user_id}:{notion_db_id}:{calendar_id}"
        cached_blocks = self.caching_service.get(cache_key)
        if cached_blocks:
            return [TimeBlock(**block) for block in cached_blocks]

        try:
            # Load and persist tasks
            tasks = self._load_and_create_tasks(db, user_id, notion_db_id)

            # Prioritize and allocate blocks
            user_ai_settings = self.features_service.get_settings(db, user_id)
            time_blocks = self._prioritize_and_allocate(tasks, db, user_id, calendar_id, start_date, end_date,
                                                        earliest_time, latest_time, user_ai_settings)

            db.commit()
            self.caching_service.set(
                cache_key,
                [block.__dict__ for block in time_blocks],
                timeout=3600
            )
            return time_blocks
        except (SQLAlchemyError, ValueError) as e:
            self.logging_service.error("Failed to generate time blocks", user_id=user_id,
                                       extra={"error": str(e), "notion_db_id": notion_db_id,
                                              "calendar_id": calendar_id})
            raise wrap_external_error(e, DatabaseError, "Failed to generate time blocks") from e

    def _load_and_create_tasks(self, db: Session, user_id: int, notion_db_id: str) -> List[Task]:
        """Load task candidates and create tasks."""
        candidates = self._load_candidates(db, user_id, notion_db_id)
        tasks = self._create_tasks_from_candidates(candidates)
        for task in tasks:
            task.urgency = self.get_urgency_score(task.title, user_id)  # NEW: Set urgency float on task creation
        self._persist_tasks(db, tasks)
        return tasks

    def _prioritize_and_allocate(self, tasks: List[Task], db: Session, user_id: int, calendar_id: str,
                                 start_date: datetime, end_date: datetime, earliest_time: str, latest_time: str,
                                 settings: UserAISettings) -> List[TimeBlock]:
        """Prioritize tasks and allocate them to free slots."""
        prioritized = self.task_prioritizer.prioritize_tasks(tasks, db)
        slots = self.free_time_finder.find_free_slots(user_id, db, calendar_id, start_date, end_date, earliest_time,
                                                      latest_time)
        time_blocks = []
        for task in prioritized:
            urgency = task.urgency or self._heuristic_urgency(task.title)  # CHANGED: Use task.urgency float if set
            duration = task.duration or 30
            if SchedulingPolicy.should_prioritize_early(urgency):
                slots = sorted(slots, key=lambda s: s.start)
            block, slots = self._try_allocate_task_to_slots(task, duration, user_id, calendar_id, slots)
            if block:
                time_blocks.append(block)
                if settings.urgency_learning_scope != 'off':
                    self._log_urgency_event(db, task, urgency, user_id)
        return time_blocks

    def _load_candidates(self, db: Session, user_id: int, notion_db_id: str) -> List[TaskCandidateData]:
        """Load task candidates from Notion database."""
        try:
            candidates = self.task_candidate_repo.get_candidates(db, user_id, notion_db_id)
            if not candidates:
                self.logging_service.error("No task candidates found", user_id=user_id,
                                           extra={"notion_db_id": notion_db_id})
                return []
            return candidates
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to load candidates", user_id=user_id,
                                       extra={"error": str(e), "notion_db_id": notion_db_id})
            raise wrap_external_error(e, DatabaseError, "Failed to load candidates") from e

    def _create_tasks_from_candidates(self, candidates: List[TaskCandidateData]) -> List[Task]:
        """Create Task entities from candidates."""
        return [Task(
            user_id=c.user_id,
            notion_db_id=c.notion_db_id,
            title=c.title,
            due_date=c.due_date,
            duration=c.duration,
            priority=c.priority,
            status=c.status
        ) for c in candidates]

    def _persist_tasks(self, db: Session, tasks: List[Task]):
        """Persist tasks to the database."""
        try:
            db.add_all(tasks)
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            self.logging_service.error("Failed to persist tasks", extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to persist tasks") from e

    def _heuristic_urgency(self, title: str) -> float:
        """Fallback urgency detection using keyword matching."""
        keywords = ['urgent', 'asap', 'immediately', 'now', 'critical', 'deadline']
        return 0.8 if any(re.search(rf'\b{word}\b', title.lower()) for word in keywords) else 0.3

    def _analyze_task_urgency(self, title: str, user_id: int) -> float:

        self._load_nlp_model()

        if not self.nlp:
            self.logging_service.error("NLP model not available, falling back to heuristic", user_id=user_id)
            return self._heuristic_urgency(title)
        try:
            result = self.nlp(title)[0]
            return result['score']
        except Exception as e:
            self.logging_service.error("Failed to analyze urgency", user_id=user_id,
                                       extra={"error": str(e), "title": title})
            return self._heuristic_urgency(title)

    def _try_allocate_task_to_slots(self, task: Task, required_minutes: int, user_id: int, calendar_id: str,
                                    slots: List[TimeBlock]) -> Tuple[Optional[TimeBlock], List[TimeBlock]]:
        for i, slot in enumerate(slots):
            slot_duration = int((slot.end - slot.start).total_seconds() / 60)
            if slot_duration >= required_minutes:
                start_time = slot.start
                end_time = start_time + timedelta(minutes=required_minutes)
                remaining_slots = slots[:i] + [
                    TimeBlock(user_id=user_id, calendar_id=calendar_id, start=end_time, end=slot.end)] + slots[i + 1:]
                remaining_slots = [s for s in remaining_slots if
                                   (s.end - s.start).total_seconds() > 0]  # Remove empties
                return TimeBlock(user_id=user_id, calendar_id=calendar_id, start=start_time, end=end_time,
                                 task_id=task.id), remaining_slots
        return None, slots


    def _log_urgency_event(self, db: Session, task: Task, urgency: float, user_id: int):
        """Log urgency feedback to AI training events."""
        try:
            event = AITrainingEvent(
                user_id=user_id,
                task_id=task.id,
                event_type='urgency_feedback',
                input_json=UrgencyFeedbackInput(title=task.title).model_dump(),
                label_json=UrgencyFeedbackLabel(urgency_score=urgency).model_dump(),
                source='model'
            )
            self.ai_data_service.log_event(db, event)
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to log urgency event", user_id=user_id, task_id=task.id,
                                       extra={"error": str(e)})

    def _load_nlp_model(self):
        if self.nlp:
            return

        self.logging_service.info("TIME_BLOCK_GENERATOR: Loading NLP model...")

        model_dir = current_app.config.get("MODEL_DIR", ".")
        model_path = os.path.join(model_dir, "KS-Vijay_urgency-model-aura")
        try:
            self.nlp = pipeline("text-classification", model=model_path, local_files_only=True)
        except OSError as e:
            self.logging_service.error(f"Missing or unreadable local model files at {model_path}",
                user_id=0,
                extra={"error": str(e)}
            )
            self.nlp = None
        except ValueError as e:
            self.logging_service.error(f"ValueError loading model at {model_path} — likely missing files or offline-only mode",
                user_id=0,
                extra={"error": str(e)}
            )
            self.nlp = None
        except EntryNotFoundError as e:
            self.logging_service.error(f"EntryNotFoundError — model lookup failed for {model_path}",
                user_id=0,
                extra={"error": str(e)}
            )
            self.nlp = None
        else:
            self.logging_service.info(f"Loaded NLP model from {model_path}")
            return