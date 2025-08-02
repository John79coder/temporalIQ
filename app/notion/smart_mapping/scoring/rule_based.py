# notion/smart_mapping/scoring/rule_based.py
from app.notion.smart_mapping.scoring.base import Scorer

class RuleBasedScorer(Scorer):
    def score(self, matches):
        return matches
