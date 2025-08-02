# notion/smart_mapping/scoring/base.py
from abc import ABC, abstractmethod

class Scorer(ABC):
    @abstractmethod
    def score(self, matches):
        pass
