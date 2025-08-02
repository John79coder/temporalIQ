# app/scheduling/services/task_prioritizer.py
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.utils.caching import ICacheService
from app.scheduling.models.entities import Task
from app.scheduling.services.interfaces import ITaskPrioritizer
from app.utils.time_zone import TimeZone
from app.utils.exceptions import DataValidationError, wrap_external_error, DatabaseError
from app.user_preferences.preferences_store.service import PreferencesService
from app.features.services.service import FeaturesService
from app.features.services.ai_data_service import AIDataService
from app.features.models.entities import AITrainingEvent
from app.utils.logging_service import LoggingService
from app.features.models.schemas import SlotChoiceInput, SlotChoiceLabel
import numpy as np
import joblib
import os
from flask import current_app
from tenacity import retry, stop_after_attempt, wait_exponential
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_score

class TaskPrioritizer(ITaskPrioritizer):
    def __init__(self, caching_service: ICacheService, features_service: FeaturesService, preferences_service: PreferencesService, ai_data_service: AIDataService, logging_service: LoggingService):
        self.caching_service = caching_service
        self.features_service = features_service
        self.preferences_service = preferences_service
        self.ai_data_service = ai_data_service
        self.logging_service = logging_service
        self.priority_weights = {"high": 3, "medium": 2, "low": 1, None: 0}
        self.model_path = os.path.join(current_app.config.get('MODEL_DIR', '.'), "task_prioritizer_model.pkl")
        self.ridge_model = self._load_model()

    def _load_model(self):
        """Load Ridge model from file or initialize new."""
        try:
            if os.path.exists(self.model_path):
                return joblib.load(self.model_path)
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
        joblib.dump(self.ridge_model, self.model_path)

    def _fetch_slot_choices(self, db: Session, user_id: int, scope: str) -> List[AITrainingEvent]:
        """Fetch slot choice events for training."""
        try:
            return self.ai_data_service.get_events_by_type(db, 'slot_choice', user_id if scope == 'user' else None)
        except DatabaseError as e:
            self.logging_service.error("Failed to fetch slot choices", user_id=user_id, extra={"error": str(e)})
            raise

    def _train_model(self, db: Session, user_id: int) -> bool:
        """Train Ridge model on slot choice data."""
        try:
            settings = self.features_service.get_settings(db, user_id)
            scope = settings.slot_ranking_learning_scope
            if scope == 'off':
                return False

            events = self._fetch_slot_choices(db, user_id, scope)
            if len(events) < 100:
                self.logging_service.info("Insufficient data for Ridge training, using fallback", user_id=user_id, extra={"event_count": len(events)})
                return False

            features, labels = [], []
            for event in events:
                try:
                    input_data = SlotChoiceInput(**event.input_json)
                    label_data = SlotChoiceLabel(**event.label_json)
                    features.append([
                        input_data.duration,
                        self.priority_weights.get(input_data.urgency, 0),
                        input_data.urgency or 0.0
                    ])
                    labels.append(1 if label_data.selected else 0)
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
                priority_score = self.priority_weights.get(task.priority, 0)
                due_date_score = 0
                if task.due_date:
                    try:
                        user_preferences = self.preferences_service.get_preferences(db, task.user_id)
                        user_time_zone = user_preferences.time_zone if user_preferences and user_preferences.time_zone else "UTC"
                        due_date = TimeZone.to_utc(task.due_date, user_time_zone)
                        due_date_score = max(0, 1 / (due_date.timestamp() - TimeZone.utc_now().timestamp() + 1))
                    except ValueError as e:
                        self.logging_service.error("Invalid due_date for task", user_id=user_id, task_id=task.id, extra={"error": str(e)})
                if use_ml:
                    try:
                        features = np.array([[task.duration or 30, priority_score, due_date_score]])
                        ml_score = self.ridge_model.predict(features)[0]
                        return (-ml_score, -priority_score, due_date_score)
                    except ValueError as e:
                        self.logging_service.error("Invalid data for Ridge prediction", user_id=user_id, task_id=task.id, extra={"error": str(e)})
                        return (-priority_score, due_date_score)
                    except Exception as e:
                        self.logging_service.error("Unexpected error in Ridge prediction", user_id=user_id, task_id=task.id, extra={"error": str(e)})
                        return (-priority_score, due_date_score)
                return (-priority_score, due_date_score)

            return sorted(tasks, key=sort_key)
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to prioritize tasks", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to prioritize tasks") from e
        except Exception as e:
            self.logging_service.error("Unexpected error in prioritizing tasks", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to prioritize tasks") from e