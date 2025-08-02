import os

from flask import current_app

from app.features.services.service import FeaturesService
from sqlalchemy.orm import Session
from typing import List, Dict
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor
from sentence_transformers import SentenceTransformer, util

class PriorityExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service
        self.model = None
        self.priorities = ["high", "medium", "low"]

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])

        if self.features_service.get_settings(db, user_id).use_embedding_similarity:
            if self.model is None:

                model_dir = current_app.config.get("MODEL_DIR", ".")
                model_path = os.path.join(model_dir, "all-MiniLM-L6-v2")
                self.model = SentenceTransformer(model_path)

            emb = self.model.encode(text)
            pri_embs = self.model.encode(self.priorities)
            sims = util.cos_sim(emb, pri_embs)[0]
            priority = self.priorities[sims.argmax()] if max(sims) > 0.5 else None
            confidence = max(sims) if priority else 0.5
        else:
            priority = next((p for p in self.priorities if p in text.lower()), None)
            confidence = 0.7 if priority else 0.5

        return PartialCandidate(priority=priority, confidence=confidence)