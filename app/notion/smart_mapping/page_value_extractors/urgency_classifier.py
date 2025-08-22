# app/notion/smart_mapping/page_value_extractors/urgency_classifier.py
import os
from typing import List, Dict

from flask import current_app
from huggingface_hub.errors import EntryNotFoundError
from sqlalchemy.orm import Session
from transformers import pipeline

from app.features.services.service import FeaturesService
from app.logging import ApplicationLogger
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor


class UrgencyClassifier(PageValueExtractor):
    def __init__(self, features_service: FeaturesService, logging_service: ApplicationLogger):
        self.features_service = features_service
        self.logging_service = logging_service
        self.nlp = None

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])

        self._load_nlp_model()

        if self.features_service.get_settings(db, user_id).use_nlp_urgency and self.nlp is not None:

            result = self.nlp(text)[0]
            urgency = result['score']
            confidence = 0.8
        else:
            urgency = 0.5  # Heuristic default
            confidence = 0.5
        return PartialCandidate(urgency=urgency,
                                confidence=confidence)

    def _load_nlp_model(self):
        if self.nlp:
            return

        self.logging_service.info("URGENCY_CLASSIFIER: Loading NLP model...")

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
