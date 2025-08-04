# services/free_time_finder.py
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.utils.caching import ICacheService
from app.utils.exceptions import CalendarError, DataValidationError, wrap_external_error, DatabaseError
from app.icloud.models.schemas import TimeBlock
from app.icloud.services.interfaces import ICalDAVEventService
from app.scheduling.services.interfaces import IFreeTimeFinder
from app.scheduling.services.time_block_generator import TimeBlockGenerator
from app.scheduling.models.policies import SchedulingPolicy
from app.features.services.service import FeaturesService
from app.features.services.ai_data_service import AIDataService
from app.features.models.entities import AITrainingEvent
from app.user_preferences.preferences_store.service import PreferencesService
from app.utils.logging_service import LoggingService
from app.features.models.schemas import DurationLogInput, DurationLogLabel

import re
import numpy as np
import joblib
import os
from flask import current_app
from tenacity import retry, stop_after_attempt, wait_exponential
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_score

from app.scheduling.models.entities import Task
from config import Config


class FreeTimeFinder(IFreeTimeFinder):
    def __init__(self, caching_service: ICacheService, event_service: ICalDAVEventService,
                 features_service: FeaturesService, preferences_service: PreferencesService,
                 ai_data_service: AIDataService, logging_service: LoggingService,
                 time_block_generator: TimeBlockGenerator):
        self.caching_service = caching_service
        self.event_service = event_service
        self.features_service = features_service
        self.preferences_service = preferences_service
        self.ai_data_service = ai_data_service
        self.logging_service = logging_service
        self.time_block_generator = time_block_generator
        self.ridge_model = self._load_model()
        self.ridge_model_trained = False

    def _load_model(self):
        """Load Ridge model from file or initialize new."""
        model_dir = current_app.config.get('MODEL_DIR', '.')
        model_path = os.path.join(model_dir, "ridge_duration_model.pkl")
        try:
            if os.path.exists(model_path):
                return joblib.load(model_path)
            return Ridge()
        except FileNotFoundError as e:
            self.logging_service.error("Ridge model file not found, initializing new", extra={"error": str(e)})
            return Ridge()
        except Exception as e:
            self.logging_service.error("Failed to load Ridge model", extra={"error": str(e)})
            return Ridge()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _save_model(self):
        """Save Ridge model with retries."""
        model_dir = current_app.config.get('MODEL_DIR', '.')
        model_path = os.path.join(model_dir, "ridge_duration_model.pkl")
        joblib.dump(self.ridge_model, model_path)

    def _fetch_events(self, db: Session, user_id: int, calendar_id: str, start_date: datetime,
                      end_date: datetime) -> List:
        """Fetch calendar events for the user."""
        try:
            return self.event_service.fetch_user_events(user_id, db, calendar_id, start_date, end_date)
        except CalendarError as e:
            self.logging_service.error("Failed to fetch calendar events", user_id=user_id,
                                       extra={"error": str(e), "calendar_id": calendar_id})
            raise

    def _train_model(self, db: Session, user_id: int) -> bool:
        """Train Ridge model on duration data."""
        try:
            settings = self.features_service.get_settings(db, user_id)
            scope = settings.duration_learning_scope
            if scope == 'off':
                return False

            events = self.ai_data_service.get_events_by_type(db, 'duration_log', user_id if scope == 'user' else None)
            if len(events) < 100:
                self.logging_service.info("Insufficient data for Ridge training, using fallback", user_id=user_id, extra={"event_count": len(events)})
                return False

            features, labels = [], []
            for event in events:
                try:
                    input_data = DurationLogInput(**event.input_json)
                    label_data = DurationLogLabel(**event.label_json)
                    features.append([
                        input_data.num_events,
                        input_data.day_length_hours,
                        input_data.urgency  # Already float
                    ])
                    labels.append(label_data.duration_minutes)
                except ValueError as e:
                    self.logging_service.error("Invalid JSON in training event", user_id=user_id, task_id=event.task_id,
                                               extra={"error": str(e), "event_id": event.id})
                    continue
            self.ridge_model.fit(np.array(features), np.array(labels))
            scores = cross_val_score(self.ridge_model, np.array(features), np.array(labels), cv=5)
            mean_cv_acc = np.mean(scores)
            if mean_cv_acc > 0.85:
                try:
                    self._save_model()
                    return True
                except Exception as e:
                    self.logging_service.error("Failed to save Ridge model", user_id=user_id, extra={"error": str(e)})
                    return False
            self.logging_service.info("Ridge model cross-validation accuracy too low, using fallback", user_id=user_id, extra={"cv_mean": mean_cv_acc})
            return False
        except SQLAlchemyError as e:
            self.logging_service.error("Database error during model training", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to train Ridge model") from e
        except ValueError as e:
            self.logging_service.error("Invalid data for training", user_id=user_id, extra={"error": str(e)})
            return False

    def _log_duration_event(self, db: Session, user_id: int, task: Optional[Task], events: List, current_time: datetime,
                            block_end: datetime, urgency: float) -> None:
        """Log duration event to AI training data."""
        try:
            event = AITrainingEvent(
                user_id=user_id,
                task_id=task.id if task else None,
                event_type='duration_log',
                input_json=DurationLogInput(
                    num_events=len(events),
                    day_length_hours=self._get_work_hours(db, user_id),
                    urgency=urgency
                ).model_dump(),
                label_json=DurationLogLabel(duration_minutes=(block_end - current_time).total_seconds() / 60).model_dump(),
                source='model'
            )
            self.ai_data_service.log_event(db, event)
        except Exception as e:
            self.logging_service.error("Failed to log duration event", user_id=user_id,
                                       task_id=task.id if task else None, extra={"error": str(e)})

    def _get_work_hours(self, db: Session, user_id: int) -> float:
        """Get user's work hours from preferences."""
        try:
            prefs = self.preferences_service.get_preferences(db, user_id)
            return float(prefs.work_hours or 8)  # Default to 8 hours
        except Exception as e:
            self.logging_service.error("Failed to get work hours", user_id=user_id, extra={"error": str(e)})
            return 8.0

    def find_free_slots(
            self,
            user_id: int,
            db: Session,
            calendar_id: str,
            start_date: datetime,
            end_date: datetime,
            earliest_time: str,
            latest_time: str
    ) -> List[TimeBlock]:
        """Find free time slots in the user's calendar."""
        try:
            cache_key = f"scheduling:free_slots:{user_id}:{calendar_id}:{start_date.isoformat()}:{end_date.isoformat()}"
            cached_slots = self.caching_service.get(cache_key)
            if cached_slots:
                return [TimeBlock(**slot) for slot in cached_slots]
            if earliest_time >= latest_time:
                raise DataValidationError("earliest_time must be before latest_time")
            self._validate_time_format(earliest_time, latest_time)

            # Fetch events and settings
            events = self._fetch_events(db, user_id, calendar_id, start_date, end_date)
            user_ai_settings = self.features_service.get_settings(db, user_id)
            use_ml = user_ai_settings.duration_learning_scope != 'off'  # FIXED: Use correct scope

            if use_ml:
                self._train_model(db, user_id)

            # Compute slots
            slots = self._compute_slots(db, user_id, events, start_date, end_date, earliest_time, latest_time, use_ml)

            db.commit()
            self.caching_service.set(
                cache_key,
                [slot.model_dump() for slot in slots],
                timeout=3600
            )
            return slots
        except (CalendarError, DataValidationError) as e:
            raise
        except SQLAlchemyError as e:
            self.logging_service.error("Database error in finding free slots", user_id=user_id,
                                       extra={"error": str(e), "calendar_id": calendar_id})
            raise wrap_external_error(e, DatabaseError, "Failed to find free slots") from e
        except Exception as e:
            self.logging_service.error("Unexpected error in finding free slots", user_id=user_id,
                                       extra={"error": str(e), "calendar_id": calendar_id})
            raise wrap_external_error(e, CalendarError, "Failed to find free slots") from e

    def _validate_time_format(self, earliest_time: str, latest_time: str):
        """Validate HH:MM format for time strings."""
        time_pattern = r"^\d{2}:\d{2}$"
        if not (re.match(time_pattern, earliest_time) and re.match(time_pattern, latest_time)):
            raise DataValidationError("Time format must be HH:MM")
        try:
            hour, minute = map(int, earliest_time.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise DataValidationError("Invalid hours or minutes in earliest_time")
            hour, minute = map(int, latest_time.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise DataValidationError("Invalid hours or minutes in latest_time")
        except ValueError as e:
            raise DataValidationError("Invalid time format") from e

    def _compute_slots(self, db: Session, user_id: int, events: List, start_date: datetime, end_date: datetime,
                       earliest_time: str, latest_time: str, use_ml: bool) -> List[TimeBlock]:
        """Compute free time slots for the given date range."""
        try:
            earliest_hour, earliest_minute = map(int, earliest_time.split(":"))
            latest_hour, latest_minute = map(int, latest_time.split(":"))
            slots = []
            current_date = start_date
            while current_date <= end_date:
                day_start = current_date.replace(hour=earliest_hour, minute=earliest_minute, second=0, microsecond=0, tzinfo=timezone.utc)
                day_end = current_date.replace(hour=latest_hour, minute=latest_minute, second=0, microsecond=0, tzinfo=timezone.utc)
                current_time = day_start
                while current_time < day_end:
                    block_end = self._compute_block_end(current_time, day_start, day_end, events, len(events), use_ml,
                                                        user_id, db, None)
                    if not self._is_overlapping(events, current_time, block_end):
                        slots.append(TimeBlock(start=current_time, end=block_end))
                        if use_ml:
                            self._log_duration_event(db, user_id, None, events, current_time, block_end, 0.0)
                    current_time = block_end
                current_date += timedelta(days=1)
            return slots
        except ValueError as e:
            self.logging_service.error("Invalid time format", user_id=user_id,
                                       extra={"error": str(e), "earliest_time": earliest_time,
                                              "latest_time": latest_time})
            raise wrap_external_error(e, DataValidationError, "Invalid time format") from e

    def _compute_block_end(self, current_time: datetime, day_start: datetime, day_end: datetime, events: List,
                           num_events: int, use_ml: bool, user_id: int, db : Session, task: Optional[Task]) -> datetime:
        """Compute the end time for a time block."""
        from app.scheduling.models.policies import get_urgency_float  # NEW: Import utility
        try:
            if use_ml:
                urgency = get_urgency_float(self.time_block_generator.get_urgency_score(task.title, user_id) if task else 0.0)  # CHANGED: Ensure float
                state = np.array([[num_events, (day_end - day_start).total_seconds() / 3600, urgency]])
                predicted_duration = self.ridge_model.predict(state)[0]
                return current_time + timedelta(minutes=SchedulingPolicy.clamp_duration(predicted_duration))
            else:
                try:
                    prefs = self.preferences_service.get_preferences(db, user_id)
                    block_size = prefs.block_size_minutes or Config.DEFAULT_BLOCK_MINUTES
                except Exception as e:
                    self.logging_service.error("Failed to get prefs in fallback, using Config default", user_id=user_id, extra={"error": str(e)})
                    block_size = Config.DEFAULT_BLOCK_MINUTES
                return current_time + timedelta(minutes=block_size)
        except ValueError as e:
            self.logging_service.error("Invalid data for Ridge prediction", user_id=user_id,
                                       task_id=task.id if task else None, extra={"error": str(e)})
            return current_time + timedelta(minutes=30)
        except Exception as e:
            self.logging_service.error("Unexpected error in Ridge prediction", user_id=user_id,
                                       task_id=task.id if task else None, extra={"error": str(e)})
            return current_time + timedelta(minutes=30)

    def _is_overlapping(self, events: List, start: datetime, end: datetime) -> bool:
        """Check if a time slot overlaps with existing events."""
        return any(
            event.start <= end and event.end > start
            for event in events
        )