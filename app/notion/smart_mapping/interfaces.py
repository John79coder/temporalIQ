# app/notion/smart_mapping/interfaces.py
from abc import ABC, abstractmethod
from typing import List, Dict

from sqlalchemy.orm import Session

from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.models import FieldMatch, TaskCandidateData


class ISchemaParser(ABC):
    @abstractmethod
    def normalize(self, notion_schema: dict) -> List[dict]:
        pass


class IFieldDetector(ABC):
    @abstractmethod
    def detect(self, fields: List[dict], rows: List[dict], db: Session, user_id: int) -> List[FieldMatch]:
        pass


class ICandidateGenerator(ABC):
    @abstractmethod
    def generate_candidates(self, data: dict, db: Session, user_id: int, database_id: str) -> List[TaskCandidateData]:
        pass

class IValueExtractor(ABC):
    @abstractmethod
    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        pass