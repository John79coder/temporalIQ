import os

from flask import current_app

from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor
from app.features.services.service import FeaturesService
from sqlalchemy.orm import Session
from typing import List, Dict
from transformers import pipeline

from app.notion.models.schemas import PartialCandidate


class UrgencyClassifier(PageValueExtractor):
    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service
        self.nlp = None

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])

        if self.features_service.get_settings(db, user_id).use_nlp_urgency:
            if self.nlp is None:

                model_dir = current_app.config.get("MODEL_DIR", ".")
                model_path = os.path.join(model_dir, "KS-Vijay/urgency-model-aura")
                self.nlp = pipeline("text-classification", model=model_path)

            result = self.nlp(text)[0]
            urgency = result['score']
            confidence = 0.8
        else:
            urgency = 0.5  # Heuristic default
            confidence = 0.5
        return PartialCandidate(urgency=urgency, confidence=confidence)  # Urgency not in schema; could add field if needed