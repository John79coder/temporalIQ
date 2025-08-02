from abc import ABC, abstractmethod
from typing import List, Dict
from sqlalchemy.orm import Session

from app.notion.models.schemas import PartialCandidate


class PageValueExtractor(ABC):
    @abstractmethod
    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        pass