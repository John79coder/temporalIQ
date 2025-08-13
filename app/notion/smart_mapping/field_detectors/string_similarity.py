# app/notion/smart_mapping/field_detectors/string_similarity.py
import os
from typing import List

import numpy as np
import torch
import torch.nn.functional as F
from flask import current_app
from sentence_transformers import SentenceTransformer
from sentence_transformers.models import Transformer, Pooling
from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.notion.smart_mapping.field_detectors.base import FieldDetector
from app.notion.smart_mapping.models import FieldMatch
from app.utils.exceptions import wrap_external_error, ServiceUnavailableError


class StringSimilarityMatcher(FieldDetector):
    target_fields = ["title", "due_date", "duration"]

    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service
        self.model = None

    def get_model(self):
        if self.model is None:
            try:
                model_dir = current_app.config.get("MODEL_DIR", ".")
                model_path = os.path.join(model_dir, "all-MiniLM-L6-v2")
                transformer = Transformer(model_name_or_path=model_path, model_args={"attn_implementation": "eager"})
                pooling = Pooling(transformer.get_word_embedding_dimension(), pooling_mode='mean')
                self.model = SentenceTransformer(modules=[transformer, pooling])
            except Exception as e:
                raise wrap_external_error(e, ServiceUnavailableError, "Failed to load embedding model")
        return self.model

    def detect(self, fields: list[dict], rows: List[dict] = None, db: Session = None, user_id: int = None) -> list[
        FieldMatch]:
        user_ai_settings = self.features_service.get_settings(db, user_id)
        use_embedding_similarity = user_ai_settings.use_embedding_similarity

        if not use_embedding_similarity:
            return self._fallback_detect(fields)

        matches = []
        field_names = [field["name"].lower() for field in fields]
        concept_names = self.target_fields

        # Embed all at once for efficiency
        field_embeds = self.get_model().encode(field_names)
        concept_embeds = self.get_model().encode(concept_names)

        for i, field in enumerate(fields):
            name_emb = field_embeds[i]
            for j, concept in enumerate(concept_names):
                sim = F.cosine_similarity(torch.tensor(np.array([name_emb])),
                                          torch.tensor(np.array([concept_embeds[j]]))).item()
                if sim > 0.5:
                    matches.append(FieldMatch(
                        notion_field=field["name"],
                        matched_concept=concept,
                        confidence=sim,
                        rationale="Embedding similarity"
                    ))
        return matches

    def _fallback_detect(self, fields: list[dict]) -> list[FieldMatch]:
        matches = []
        for field in fields:
            name_lower = field["name"].lower()
            for concept in self.target_fields:
                if concept in name_lower:
                    matches.append(FieldMatch(
                        notion_field=field["name"],
                        matched_concept=concept,
                        confidence=0.7,
                        rationale="String partial match"
                    ))
        return matches
