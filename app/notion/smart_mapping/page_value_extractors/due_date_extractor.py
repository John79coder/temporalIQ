from typing import List, Dict

from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor
from app.utils.date_parser import custom_parse_date


class DueDateExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])
        due_date = custom_parse_date(text)
        confidence = 0.8 if due_date else 0.0
        return PartialCandidate(due_date=due_date, confidence=confidence)
