# app/notion/smart_mapping/scoring/ml_model.py
import os
from flask import current_app
from app.notion.smart_mapping.scoring.base import Scorer
from app.notion.smart_mapping.models import FieldMatch
import spacy
from sqlalchemy.orm import Session
from app.features.services.service import FeaturesService


class MLModelScorer(Scorer):
    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service
        self.target_concepts = {
            "title": "title",
            "due_date": "due date",
            "duration": "duration",
            "priority": "priority",
            "status": "status",
            "assignee": "assignee",
            "tags": "tags",
            "created_at": "created at",
            "updated_at": "updated at",
            "notes": "notes"
        }
        model_dir = current_app.config.get("MODEL_DIR", ".")
        model_path = os.path.join(model_dir, "en_core_web_sm")
        self.nlp = spacy.load(model_path)

    def score(self, matches, db: Session = None, user_id: int = None):
        if db and user_id:
            settings = self.features_service.get_settings(db, user_id)
            if not settings.use_nlp_scoring:
                return matches
        enriched = []
        for match in matches:
            if match.matched_concept not in self.target_concepts:
                continue  # Skip matches with invalid concepts
            source_doc = self.nlp(match.notion_field.lower())
            target_doc = self.nlp(self.target_concepts[match.matched_concept])
            similarity = source_doc.similarity(target_doc)
            # Boost score by averaging existing confidence and similarity
            adjusted = FieldMatch(
                notion_field=match.notion_field,
                matched_concept=match.matched_concept,
                confidence=round((match.confidence + similarity) / 2, 3),
                rationale=f"{match.rationale}; NLP similarity: {similarity:.2f}"
            )
            enriched.append(adjusted)
        return enriched