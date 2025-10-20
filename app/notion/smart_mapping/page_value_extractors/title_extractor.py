import os
from typing import List, Dict

import spacy
from flask import current_app
from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor

# Logging
from app.logging import ApplicationLogger


class TitleExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService, application_logger: ApplicationLogger):
        self.features_service = features_service
        self.application_logger = application_logger
        self.nlp = None

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])


        self.application_logger.debug(
            "TITLE_EXTRACTOR.start",
            user_id=user_id,
            text_len=len(text),
        )

        if self.features_service.get_settings(db, user_id).use_spacy_heuristics:
            if self.nlp is None:
                model_dir = current_app.config.get("MODEL_DIR", ".")
                model_path = os.path.join(model_dir, "en_core_web_sm")
                self.nlp = spacy.load(model_path)
                self.application_logger.debug("TITLE_EXTRACTOR.path", user_id=user_id, path="spacy_init_done")

            doc = self.nlp(text)
            title = " ".join([token.text for token in doc if token.pos_ in ['NOUN', 'PROPN']]) or text[:50]
            confidence = 0.8
            path = "spacy"
        else:
            title = text[:50] or "Untitled"
            confidence = 0.5
            path = "substring"

        self.application_logger.debug(
            "TITLE_EXTRACTOR.result",
            user_id=user_id,
            path=path,
            title_preview=title[:60] if title else None,
            confidence=confidence,
        )

        return PartialCandidate(title=title, confidence=confidence)
