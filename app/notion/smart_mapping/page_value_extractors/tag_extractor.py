import os
import re

from flask import current_app

from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor
from app.features.services.service import FeaturesService
from sqlalchemy.orm import Session
from typing import List, Dict
from app.notion.models.schemas import PartialCandidate
import spacy

class TagExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service
        self.nlp = None

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])

        if self.features_service.get_settings(db, user_id).use_spacy_heuristics:
            if self.nlp is None:

                model_dir = current_app.config.get("MODEL_DIR", ".")
                model_path = os.path.join(model_dir, "en_core_web_md")
                self.nlp = spacy.load(model_path)

            doc = self.nlp(text)
            tags = [ent.text for ent in doc.ents if ent.label_ in ['ORG', 'PRODUCT', 'EVENT']]
            confidence = 0.8 if tags else 0.5
        else:
            tags = re.findall(r'#(\w+)', text)
            confidence = 0.7 if tags else 0.5
        return PartialCandidate(tags=tags, confidence=confidence)