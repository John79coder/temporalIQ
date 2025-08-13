# notion/smart_mapping/field_detectors/base.py
from abc import ABC, abstractmethod
from typing import List, Optional

from sqlalchemy.orm.session import Session


class FieldDetector(ABC):
    @abstractmethod
    def detect(self, fields: list[dict], rows: Optional[List[dict]] = None, db: Optional[Session] = None) -> list:
        pass
