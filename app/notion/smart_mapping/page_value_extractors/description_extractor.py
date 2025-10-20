import os
from typing import List, Dict

import spacy
from flask import current_app
from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor

from app.logging import ApplicationLogger


class DescriptionExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService, application_logger: ApplicationLogger):
        self.features_service = features_service
        self.application_logger = application_logger
        self.nlp = None

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join(
            [b.get('text', [{}])[0].get('plain_text', '') if b.get('type') == 'paragraph' and b.get('text') else '' for
             b in section_blocks])

        try:
            logger = current_app.extensions['app_context'].get_service('app_logger')
        except Exception:
            logger = ApplicationLogger()

        logger.debug(
            "DESCRIPTION_EXTRACTOR.start",
            user_id=user_id,
            text_len=len(text),
        )

        if self.features_service.get_settings(db, user_id).use_spacy_heuristics:
            if self.nlp is None:
                model_dir = current_app.config.get("MODEL_DIR", ".")
                model_path = os.path.join(model_dir, "en_core_web_md")
                self.nlp = spacy.load(model_path)
                logger.debug("DESCRIPTION_EXTRACTOR.path", user_id=user_id, path="spacy_init_done")

            doc = self.nlp(text)
            description = " ".join([sent.text for sent in doc.sents])[:500]
            confidence = 0.8 if description else 0.5
            path = "spacy"
        else:
            description = text[:500]
            confidence = 0.6 if description else 0.5
            path = "substring"

        logger.debug(
            "DESCRIPTION_EXTRACTOR.result",
            user_id=user_id,
            path=path,
            desc_len=len(description or ""),
            confidence=confidence,
        )

        return PartialCandidate(description=description, confidence=confidence)
