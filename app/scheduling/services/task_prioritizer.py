# app/scheduling/services/task_prioritizer.py
import os
from pickle import UnpicklingError
from typing import List

import joblib
import numpy as np
from flask import current_app
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_score
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential

from app.features.models.entities import AITrainingEvent
from app.features.models.schemas import SlotChoiceInput, SlotChoiceLabel
from app.features.services.ai_data_service import AIDataService
from app.features.services.service import FeaturesService
from app.logging import ApplicationLogger
from app.scheduling.models.entities import Task
from app.scheduling.models.policies import get_urgency_float, PRIORITY_TO_WEIGHT  # NEW: Import mappings
from app.scheduling.services.interfaces import ITaskPrioritizer
from app.user_preferences.preferences_store.service import PreferencesService
from app.utils.caching import ICacheService
from app.utils.exceptions import DataValidationError, wrap_external_error, DatabaseError
from app.utils.time_zone import TimeZone


class TaskPrioritizer(ITaskPrioritizer):
    def __init__(self, caching_service: ICacheService, features_service: FeaturesService,
                 preferences_service: PreferencesService, ai_data_service: AIDataService,
                 logging_service: ApplicationLogger):
        self.caching_service = caching_service
        self.features_service = features_service
        self.preferences_service = preferences_service
        self.ai_data_service = ai_data_service
        self.logging_service = logging_service
        self.priority_weights = {"high": 3, "medium": 2, "low": 1, None: 0}
        self.model_path = os.path.join(current_app.config.get('MODEL_DIR', '.'), "task_prioritizer_model.pkl")
        self.ridge_model = None

    def _load_model(self) -> Ridge:
        if self.ridge_model is not None:
            return self.ridge_model

        self.logging_service.info("Loading Ridge model...")

        model_dir = os.path.dirname(self.model_path) or "."
        try:
            if not os.path.isdir(model_dir):
                os.makedirs(model_dir, exist_ok=True)

            if os.path.exists(self.model_path):
                self.ridge_model = joblib.load(self.model_path)  # may raise EOFError/ValueError/UnpicklingError
            else:
                self.ridge_model = Ridge()

            self.logging_service.info("Ridge model loaded")
            return self.ridge_model

        except (FileNotFoundError, EOFError, ValueError, UnpicklingError, Exception) as e:
            self.logging_service.error(
                "Failed to load Ridge model; falling back to fresh model",
                extra={"error": str(e)}
            )
            self.ridge_model = Ridge()
            return self.ridge_model


    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _save_model(self):

        if self.ridge_model is None:
            return

        os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
        joblib.dump(self.ridge_model, self.model_path)

    def _fetch_slot_choices(self, db: Session, user_id: int, scope: str) -> List[AITrainingEvent]:
        """Fetch slot choice events for training."""
        try:
            return self.ai_data_service.get_events_by_type(db, 'slot_choice', user_id if scope == 'user' else None)
        except DatabaseError as e:
            self.logging_service.error("Failed to fetch slot choices", user_id=user_id, extra={"error": str(e)})
            raise

    def _train_model(self, db: Session, user_id: int) -> bool:

        try:
            settings = self.features_service.get_settings(db, user_id)
            scope = settings.slot_ranking_learning_scope
            if scope == 'off':
                return False

            events = self._fetch_slot_choices(db, user_id, scope)
            if len(events) < 100:
                self.logging_service.info("Insufficient data for Ridge training, using fallback", user_id=user_id,
                                          extra={"event_count": len(events)})
                return False

            features, labels = [], []
            for event in events:
                try:
                    input_data = SlotChoiceInput(**event.input_json)
                    label_data = SlotChoiceLabel(**event.label_json)
                    urgency_float = get_urgency_float(input_data.urgency)  # CHANGED: Convert to float
                    features.append([
                        input_data.duration,
                        PRIORITY_TO_WEIGHT.get(input_data.urgency, 0),  # CHANGED: Use str urgency for weight (int)
                        urgency_float  # Now float
                    ])
                    labels.append(1 if label_data.selected else 0)
                except ValueError as e:
                    self.logging_service.error("Invalid JSON in training event", user_id=user_id, task_id=event.task_id,
                                               extra={"error": str(e), "event_id": event.id})
                    continue

            self.ridge_model = self._load_model()

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
            self.logging_service.info("Ridge model cross-validation accuracy too low, using fallback", user_id=user_id,
                                      extra={"cv_mean": mean_cv_acc})
            return False
        except SQLAlchemyError as e:
            self.logging_service.error("Database error during model training", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to train Ridge model") from e
        except ValueError as e:
            self.logging_service.error("Invalid data for training", user_id=user_id, extra={"error": str(e)})
            return False
        except Exception as e:
            self.logging_service.error("Unexpected error in model training", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to train Ridge model") from e

    def prioritize_tasks(self, tasks: List[Task], db: Session = None) -> List[Task]:
        """Prioritize tasks based on priority and due date."""
        if not tasks or db is None:
            raise DataValidationError("Tasks and database session are required")
        user_id = tasks[0].user_id
        if not user_id:
            raise DataValidationError("User ID is required")
        try:
            settings = self.features_service.get_settings(db, user_id)
            use_ml = settings.slot_ranking_learning_scope != 'off'

            if use_ml:
                self._train_model(db, user_id)

            def sort_key(task: Task):
                priority_score = PRIORITY_TO_WEIGHT.get(task.priority, 0)  # CHANGED: Use mapping for int
                due_date_score = 0
                if task.due_date:
                    try:
                        user_preferences = self.preferences_service.get_preferences(db, task.user_id)
                        user_time_zone = user_preferences.time_zone if user_preferences and user_preferences.time_zone else "UTC"
                        due_date = TimeZone.to_utc(task.due_date, user_time_zone)
                        due_date_score = max(0, 1 / (due_date.timestamp() - TimeZone.utc_now().timestamp() + 1))
                    except ValueError as e:
                        self.logging_service.error("Invalid due_date for task", user_id=user_id, task_id=task.id,
                                                   extra={"error": str(e)})
                if use_ml:
                    try:
                        urgency_float = get_urgency_float(
                            task.urgency or task.priority)  # CHANGED: Prefer task.urgency float if set, else convert priority
                        features = np.array([[task.duration or 30, priority_score, due_date_score]])
                        ml_score = self.ridge_model.predict(features)[0]
                        return (-ml_score, -priority_score, due_date_score)
                    except ValueError as e:
                        self.logging_service.error("Invalid data for Ridge prediction", user_id=user_id,
                                                   task_id=task.id, extra={"error": str(e)})
                        return (-priority_score, due_date_score)
                    except Exception as e:
                        self.logging_service.error("Unexpected error in Ridge prediction", user_id=user_id,
                                                   task_id=task.id, extra={"error": str(e)})
                        return (-priority_score, due_date_score)
                return (-priority_score, due_date_score)

            return sorted(tasks, key=sort_key)
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to prioritize tasks", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to prioritize tasks") from e
        except Exception as e:
            self.logging_service.error("Unexpected error in prioritizing tasks", user_id=user_id,
                                       extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to prioritize tasks") from e
