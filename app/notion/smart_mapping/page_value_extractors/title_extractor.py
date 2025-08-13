import os
from typing import List, Dict

import spacy
from flask import current_app
from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor


class TitleExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service
        self.nlp = None

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])

        if self.features_service.get_settings(db, user_id).use_spacy_heuristics:
            if self.nlp is None:
                model_dir = current_app.config.get("MODEL_DIR", ".")
                model_path = os.path.join(model_dir, "en_core_web_sm")
                self.nlp = spacy.load(model_path)

            doc = self.nlp(text)
            title = " ".join([token.text for token in doc if token.pos_ in ['NOUN', 'PROPN']]) or text[:50]
            confidence = 0.8
        else:
            title = text[:50] or "Untitled"
            confidence = 0.5
        return PartialCandidate(title=title, confidence=confidence)
