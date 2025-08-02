from abc import ABC, abstractmethod
from typing import Optional, Any

class FieldValueParser(ABC):
    @abstractmethod
    def parse(self, text: str) -> Optional[Any]:
        pass
