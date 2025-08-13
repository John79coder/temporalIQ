# app/notion/smart_mapping/field_detectors/learned_detector.py
import os
import traceback
from typing import List

import joblib
from flask import current_app
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split, cross_val_score
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential

from app.features.models.entities import AITrainingEvent
from app.features.models.schemas import MappingFeedbackLabel, MappingFeedbackInput
from app.features.services.ai_data_service import AIDataService
from app.features.services.service import FeaturesService
from app.notion.mapping_storage.feedback import FeedbackLog
from app.notion.mapping_storage.feedback import FeedbackRepository
from app.notion.smart_mapping.field_detectors.base import FieldDetector
from app.notion.smart_mapping.models import FieldMatch
from app.utils.exceptions import wrap_external_error, ServiceUnavailableError, DatabaseError
from app.utils.logging_service import LoggingService


class LearnedDetector(FieldDetector):
    def __init__(self, features_service: FeaturesService, ai_data_service: AIDataService,
                 logging_service: LoggingService):
        self.features_service = features_service
        self.ai_data_service = ai_data_service
        self.logging_service = logging_service
        self.model = None
        self.vectorizer = None
        self.trained = False

    def _fetch_feedback(self, db: Session, user_id: int, scope: str) -> List:
        """Fetch feedback data for training based on scope."""
        try:
            repo = FeedbackRepository()
            return repo.get_all_feedback(db) if scope == 'global' else db.query(FeedbackLog).filter_by(
                user_id=user_id).all()
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to fetch feedback", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to fetch feedback") from e

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _save_model(self):
        """Save model with retries."""
        model_dir = current_app.config.get('MODEL_DIR', '.')
        model_path = os.path.join(model_dir, "learned_model.pkl")
        joblib.dump((self.vectorizer, self.model), model_path)

    def _train_model(self, db: Session, user_id: int) -> bool:
        """Train RandomForest model on feedback data."""
        settings = self.features_service.get_settings(db, user_id)
        if not settings.use_learned_detector or settings.mapping_learning_scope == 'off':
            return False
        try:
            feedbacks = []
            offset = 0
            limit = 1000  # Batch size for pagination
            while True:
                if settings.mapping_learning_scope == 'global':
                    batch = FeedbackRepository.get_all_feedback(db, limit=limit, offset=offset)
                else:
                    query = db.query(FeedbackLog).filter_by(user_id=user_id)
                    batch = query.offset(offset).limit(limit).all()
                if not batch:
                    break
                feedbacks.extend(batch)
                offset += limit

            if len(feedbacks) < 50:
                self.logging_service.info("Insufficient feedback for training, using fallback", user_id=user_id,
                                          extra={"feedback_count": len(feedbacks)})
                return False
            fields, concepts = zip(
                *[(f.notion_field + (" " + f.feedback_text if f.feedback_text else ""), f.corrected_concept) for f in
                  feedbacks])
            X_train, X_test, y_train, y_test = train_test_split(fields, concepts, test_size=0.2, random_state=42)
            self.vectorizer = TfidfVectorizer()
            X_train_vec = self.vectorizer.fit_transform(X_train)
            self.model = RandomForestClassifier(n_estimators=100, random_state=42)
            self.model.fit(X_train_vec, y_train)
            X_test_vec = self.vectorizer.transform(X_test)
            preds = self.model.predict(X_test_vec)
            acc = accuracy_score(y_test, preds)
            if acc < 0.85:
                self.logging_service.info("Model accuracy too low on holdout, using fallback", user_id=user_id,
                                          extra={"accuracy": acc})
                return False
            scores = cross_val_score(self.model, X_train_vec, y_train, cv=5)
            if scores.mean() < 0.85:
                self.logging_service.info("Cross-validation score too low, using fallback", user_id=user_id,
                                          extra={"cv_mean": scores.mean()})
                return False
            try:
                self._save_model()
                self.trained = True
                return True
            except Exception as e:
                self.logging_service.error("Failed to save model", user_id=user_id, extra={"error": str(e)})
                return False
        except ValueError as e:
            self.logging_service.error("Invalid data for training", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to train learned model") from e
        except SQLAlchemyError as e:
            self.logging_service.error("Database error during training", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to train learned model") from e

    def _log_mapping_event(self, db: Session, user_id: int, field_name: str, concept: str):
        """Log mapping feedback to AI training events."""
        try:
            event = AITrainingEvent(
                user_id=user_id,
                event_type='mapping_feedback',
                input_json=MappingFeedbackInput(field_name=field_name).model_dump(),
                label_json=MappingFeedbackLabel(concept=concept).model_dump(),
                source='model'
            )
            self.ai_data_service.log_event(db, event)
        except Exception as e:
            self.logging_service.error("Failed to log mapping event", user_id=user_id,
                                       extra={"error": str(e), "field_name": field_name})

    def detect(self, fields: list[dict], rows: List[dict] = None, db: Session = None, user_id: int = None) -> list[
        FieldMatch]:
        """Detect field-to-concept mappings using trained model."""
        user_ai_settings = self.features_service.get_settings(db, user_id)
        if not user_ai_settings.use_learned_detector or user_ai_settings.mapping_learning_scope == 'off':
            return []

        try:
            self._train_model(db, user_id)
            if not self.trained:
                try:
                    model_dir = current_app.config.get('MODEL_DIR', '.')
                    self.vectorizer, self.model = joblib.load(os.path.join(model_dir, "learned_model.pkl"))
                    self.trained = True
                except FileNotFoundError:
                    self.logging_service.error("No trained model available", user_id=user_id)
                    return []
                except Exception as e:
                    self.logging_service.error("Failed to load model", user_id=user_id, extra={"error": str(e)})
                    return []

            field_names = [field["name"] for field in fields]
            vecs = self.vectorizer.transform(field_names)
            preds = self.model.predict(vecs)
            probas = self.model.predict_proba(vecs)
            matches = []
            try:
                with db.begin(nested=True):
                    for i, pred in enumerate(preds):
                        conf = max(probas[i])
                        if conf > 0.5:
                            matches.append(FieldMatch(
                                notion_field=field_names[i],
                                matched_concept=pred,
                                confidence=conf,
                                rationale="Learned from feedback"
                            ))
                            if user_ai_settings.mapping_learning_scope != 'off':
                                self._log_mapping_event(db, user_id, field_names[i], pred)
            except SQLAlchemyError as e:
                self.logging_service.error("Transaction failed in detection logging", user_id=user_id,
                                           extra={"error": str(e)})
                raise wrap_external_error(e, DatabaseError, "Failed to log mapping events") from e
            return matches
        except ValueError as e:
            self.logging_service.error("Invalid input for detection", user_id=user_id,
                                       extra={"error": str(e), "fields": field_names})
            return []
        except SQLAlchemyError as e:
            self.logging_service.error("Database error in detection", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed in detection process") from e
        except Exception as e:
            print("\n")
            self.logging_service.error("Unexpected error in detection", user_id=user_id, extra={"error": str(e)})
            print(str(e))
            traceback.print_exc()
            print("\n")
            return []
