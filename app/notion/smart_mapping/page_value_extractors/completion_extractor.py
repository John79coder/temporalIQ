import re
from typing import List, Dict

from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor


class CompletionExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])
        status = "done" if re.search(r'\b(done|completed|finished)\b', text.lower()) else "todo"
        confidence = 0.7
        return PartialCandidate(status=status, confidence=confidence)
