# app/notion/smart_mapping/page_value_extractors/urgency_classifier.py
import json
import os
from typing import List, Dict

from flask import current_app, has_request_context, request, g
from huggingface_hub.errors import EntryNotFoundError
from sqlalchemy.orm import Session
from transformers import pipeline

from app.features.services.service import FeaturesService
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor


def _get_correlation_id() -> str | None:
    if not has_request_context():
        return None
    return getattr(g, "correlation_id", None) or request.headers.get("X-Correlation-ID")


def _log_event(logger, level, event: str, **fields) -> None:
    payload = {
        "event": event,
        "correlation_id": _get_correlation_id(),
        **fields,
    }
    logger.log(level, json.dumps(payload))


class UrgencyClassifier(PageValueExtractor):
    def __init__(self, features_service: FeaturesService):
        self.features_service = features_service
        self.logger = current_app.logger
        self.nlp = None

    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join(
            b.get("text", [{}])[0].get("plain_text", "") if b.get("text") else ""
            for b in section_blocks
        )

        self._load_nlp_model()

        settings = self.features_service.get_settings(db, user_id)
        if settings.use_nlp_urgency and self.nlp is not None:
            result = self.nlp(text)[0]
            urgency = result["score"]
            confidence = 0.8
            _log_event(
                self.logger,
                20,  # logging.INFO
                "urgency_classifier.inference_success",
                user_id=user_id,
                urgency=urgency,
                label=result.get("label"),
            )
        else:
            urgency = 0.5
            confidence = 0.5
            _log_event(
                self.logger,
                20,
                "urgency_classifier.inference_fallback",
                user_id=user_id,
                use_nlp_urgency=settings.use_nlp_urgency,
                model_loaded=self.nlp is not None,
            )

        return PartialCandidate(urgency=urgency, confidence=confidence)

    def _load_nlp_model(self):
        if self.nlp:
            return

        _log_event(
            self.logger,
            20,  # logging.INFO
            "urgency_classifier.model_load_start",
        )

        model_dir = current_app.config.get("MODEL_DIR", ".")
        model_path = os.path.join(model_dir, "KS-Vijay_urgency-model-aura")

        try:
            self.nlp = pipeline("text-classification", model=model_path, local_files_only=True)

        except OSError as e:
            _log_event(
                self.logger,
                40,  # logging.ERROR
                "urgency_classifier.model_load_os_error",
                model_path=model_path,
                error=str(e),
            )
            self.nlp = None

        except ValueError as e:
            _log_event(
                self.logger,
                40,
                "urgency_classifier.model_load_value_error",
                model_path=model_path,
                error=str(e),
            )
            self.nlp = None

        except EntryNotFoundError as e:
            _log_event(
                self.logger,
                40,
                "urgency_classifier.model_load_entry_not_found",
                model_path=model_path,
                error=str(e),
            )
            self.nlp = None

        else:
            _log_event(
                self.logger,
                20,
                "urgency_classifier.model_load_success",
                model_path=model_path,
            )
