# app/notion/smart_mapping/page_value_extractors/priority_extractor.py
import os
from typing import List, Dict

from flask import current_app
from sentence_transformers import SentenceTransformer, util
from sentence_transformers.models import Transformer, Pooling
from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor

# Logging
from app.logging import ApplicationLogger


class PriorityExtractor(PageValueExtractor):
    def __init__(self, features_service: FeaturesService, application_logger: ApplicationLogger):
        self.features_service = features_service
        self.application_logger = application_logger
        self.model = None
        self.priorities = ["high", "medium", "low"]

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])

        use_embeddings = self.features_service.get_settings(db, user_id).use_embedding_similarity
        self.application_logger.debug(
            "PRIORITY_EXTRACTOR.start",
            user_id=user_id,
            text_len=len(text),
            use_embedding_similarity=bool(use_embeddings),
        )

        # Existing behavior preserved
        if use_embeddings:
            if self.model is None:
                model_dir = current_app.config.get("MODEL_DIR", ".")
                model_path = os.path.join(model_dir, "all-MiniLM-L6-v2")
                transformer = Transformer(model_name_or_path=model_path, model_args={"attn_implementation": "eager"})
                pooling = Pooling(transformer.get_word_embedding_dimension(), pooling_mode='mean')
                self.model = SentenceTransformer(modules=[transformer, pooling])
                self.application_logger.debug("PRIORITY_EXTRACTOR.path", user_id=user_id, path="embedding_init_done")

            emb = self.model.encode(text)
            pri_embs = self.model.encode(self.priorities)
            sims = util.cos_sim(emb, pri_embs)[0]
            max_sim = float(max(sims)) if len(sims) else 0.0
            priority = self.priorities[sims.argmax()] if max_sim > 0.5 else None
            confidence = max_sim if priority else 0.5

            self.application_logger.debug(
                "PRIORITY_EXTRACTOR.result",
                user_id=user_id,
                path="embedding",
                priority=priority,
                confidence=confidence,
                max_sim=max_sim,
            )
        else:
            priority = next((p for p in self.priorities if p in text.lower()), None)
            confidence = 0.7 if priority else 0.5

            self.application_logger.debug(
                "PRIORITY_EXTRACTOR.result",
                user_id=user_id,
                path="keyword",
                priority=priority,
                confidence=confidence,
            )

        return PartialCandidate(priority=priority, confidence=confidence)
