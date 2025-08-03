# app/notion/smart_mapping/field_detectors/field_type_heuristics.py
import os

from flask import current_app
from sqlalchemy.orm.session import Session

from app.notion.smart_mapping.field_detectors.base import FieldDetector
from app.notion.smart_mapping.models import FieldMatch
from app.utils.exceptions import wrap_external_error, ServiceUnavailableError

import spacy
from typing import List, Optional
import pandas as pd

from app.features.services.service import FeaturesService


class FieldTypeHeuristics(FieldDetector):
    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service
        self.nlp = None
        try:
            model_dir = current_app.config.get("MODEL_DIR", ".")
            model_path = os.path.join(model_dir, "en_core_web_md")
            working_dir = os.getcwd()
            self.nlp = spacy.load(model_path)

        except Exception as e:
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to load spaCy model")

    def detect(self, fields: list[dict], rows: Optional[List[dict]] = None, db: Optional[Session] = None, user_id: Optional[int] = None) -> list[FieldMatch]:

        user_ai_settings = self.features_service.get_settings(db, user_id)
        use_spacy = user_ai_settings.use_spacy_heuristics

        matches = []
        for field in fields:
            if use_spacy and self.nlp:
                doc = self.nlp(field["name"].lower())
                pos_tags = [token.pos_ for token in doc]
                ner_ents = [ent.label_ for ent in doc.ents]

                if field["type"] == "date" or 'DATE' in ner_ents:
                    matches.append(FieldMatch(
                        notion_field=field["name"],
                        matched_concept="due_date",
                        confidence=0.8 if 'DATE' in ner_ents else 0.7,
                        rationale="Heuristic: Notion field type is date or NER tagged as DATE"
                    ))
                elif field["type"] == "number":
                    base_conf = 0.7
                    rationale = "Heuristic: Notion field type is number"
                    if rows:
                        values = [row.get('properties', {}).get(field["name"], {}).get('number') for row in rows]
                        values = [v for v in values if v is not None]
                        if values:
                            df = pd.Series(values)
                            stats = df.describe()
                            if 0 < stats['mean'] < 1440 and stats['std'] < stats['mean']:
                                base_conf += 0.2
                                rationale += "; Sample stats suggest duration (min-mean-max reasonable)"
                    matches.append(FieldMatch(
                        notion_field=field["name"],
                        matched_concept="duration",
                        confidence=min(base_conf, 1.0),
                        rationale=rationale
                    ))
                if 'NOUN' in pos_tags and field["type"] == "text":
                    matches.append(FieldMatch(
                        notion_field=field["name"],
                        matched_concept="title",
                        confidence=0.6,
                        rationale="Heuristic: POS tagged as NOUN and text type"
                    ))
            else:
                # Fallback without spaCy
                if field["type"] == "date":
                    matches.append(FieldMatch(
                        notion_field=field["name"],
                        matched_concept="due_date",
                        confidence=0.7,
                        rationale="Heuristic: Notion field type is date"
                    ))
                elif field["type"] == "number":
                    base_conf = 0.7
                    rationale = "Heuristic: Notion field type is number"
                    matches.append(FieldMatch(
                        notion_field=field["name"],
                        matched_concept="duration",
                        confidence=min(base_conf, 1.0),
                        rationale=rationale
                    ))
                if field["type"] == "text":
                    matches.append(FieldMatch(
                        notion_field=field["name"],
                        matched_concept="title",
                        confidence=0.6,
                        rationale="Heuristic: text type"
                    ))
        return matches