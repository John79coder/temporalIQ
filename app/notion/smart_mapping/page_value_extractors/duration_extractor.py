import re
from typing import List, Dict

from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.logging import ApplicationLogger
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor


class DurationExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService, application_logger: ApplicationLogger):
        self.features_service = features_service
        self.application_logger = application_logger

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])

        self.application_logger.debug(
            "DURATION_EXTRACTOR.start",
            user_id=user_id,
            text_len=len(text),
        )

        match = re.search(r'(\d+)\s*(hour|min|day)', text.lower())
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            duration = num if unit == 'min' else num * 60 if unit == 'hour' else num * 480  # 8h day
            confidence = 0.8
        else:
            duration = None
            confidence = 0.5

        self.application_logger.debug(
            "DURATION_EXTRACTOR.result",
            user_id=user_id,
            has_duration=bool(duration),
            parsed_unit=(match.group(2) if match else None),
            parsed_value=(int(match.group(1)) if match else None),
            minutes=duration,
            confidence=confidence,
        )

        return PartialCandidate(duration=duration, confidence=confidence)
