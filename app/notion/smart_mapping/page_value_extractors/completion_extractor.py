import re
from typing import List, Dict

from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor

from app.logging import ApplicationLogger


class CompletionExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService, application_logger: ApplicationLogger):
        self.features_service = features_service
        self.application_logger = application_logger

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])

        self.application_logger.debug(
            "COMPLETION_EXTRACTOR.start",
            user_id=user_id,
            text_len=len(text),
        )

        status = "done" if re.search(r'\b(done|completed|finished)\b', text.lower()) else "todo"
        confidence = 0.7

        self.application_logger.debug(
            "COMPLETION_EXTRACTOR.result",
            user_id=user_id,
            status=status,
            confidence=confidence,
        )

        return PartialCandidate(status=status, confidence=confidence)
