# app/notion/smart_mapping/page_value_extractors/urgency_classifier.py
import os
import traceback
from typing import List, Dict

from flask import current_app
from huggingface_hub.errors import EntryNotFoundError
from sqlalchemy.orm import Session
from transformers import pipeline

from app.features.services.service import FeaturesService
from app.logging import ApplicationLogger
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.page_value_extractors.base import PageValueExtractor


class UrgencyClassifier(PageValueExtractor):
    def __init__(self, features_service: FeaturesService, logging_service: ApplicationLogger):
        self.features_service = features_service
        self.logging_service = logging_service
        self.nlp = None

    # app/notion/smart_mapping/page_value_extractors/urgency_classifier.py
    def extract(self, section_blocks: List[Dict], db: Session, user_id: int) -> PartialCandidate:
        text = " ".join([b.get('text', [{}])[0].get('plain_text', '') if b.get('text') else '' for b in section_blocks])

        self._load_nlp_model()

        if self.features_service.get_settings(db, user_id).use_nlp_urgency and self.nlp is not None:
            try:
                # Add detailed logging before inference
                self.logging_service.debug(
                    "URGENCY_CLASSIFIER: Attempting inference",
                    user_id=user_id,
                    extra={
                        "text_length": len(text),
                        "text_sample": text[:100],
                        "model_type": type(self.nlp).__name__ if self.nlp else "None"
                    }
                )

                # Run inference
                result = self.nlp(text)

                # Log the raw result structure
                self.logging_service.debug(
                    "URGENCY_CLASSIFIER: Raw inference result",
                    user_id=user_id,
                    extra={
                        "result_type": type(result).__name__,
                        "result_length": len(result) if hasattr(result, '__len__') else "N/A",
                        "first_item": str(result[0]) if result else "Empty"
                    }
                )

                # Extract score - this might be where it fails
                if isinstance(result, list) and len(result) > 0:
                    first_result = result[0]
                    if isinstance(first_result, dict):
                        urgency = first_result.get('score', 0.5)
                        label = first_result.get('label', 'unknown')
                        self.logging_service.info(
                            "URGENCY_CLASSIFIER: Successful inference",
                            user_id=user_id,
                            extra={"urgency": urgency, "label": label}
                        )
                    else:
                        self.logging_service.warning(
                            "URGENCY_CLASSIFIER: Unexpected result format",
                            user_id=user_id,
                            extra={"result_type": type(first_result).__name__}
                        )
                        urgency = 0.5
                else:
                    urgency = 0.5

                confidence = 0.8

            except KeyError as e:
                self.logging_service.error(
                    "URGENCY_CLASSIFIER: Missing expected key in result",
                    user_id=user_id,
                    extra={"missing_key": str(e), "text_sample": text[:100]}
                )
                urgency = 0.5
                confidence = 0.5

            except IndexError as e:
                self.logging_service.error(
                    "URGENCY_CLASSIFIER: Empty or invalid result array",
                    user_id=user_id,
                    extra={"error": str(e), "text_sample": text[:100]}
                )
                urgency = 0.5
                confidence = 0.5



            except Exception as e:

                self.logging_service.error(

                    "URGENCY_CLASSIFIER: inference failed; falling back to heuristic",

                    user_id=user_id,

                    error_type=type(e).__name__,

                    error_message=str(e),

                    text_sample=text[:100] if text else "Empty",

                    text_length=len(text)

                )

                urgency = 0.5

                confidence = 0.5
        else:
            urgency = 0.5
            confidence = 0.5

        return PartialCandidate(urgency=urgency, confidence=confidence)

    def _load_nlp_model(self):
        if self.nlp:
            return

        self.logging_service.info("URGENCY_CLASSIFIER: Loading NLP model...")

        model_dir = current_app.config.get("MODEL_DIR", ".")
        model_path = os.path.join(model_dir, "KS-Vijay_urgency-model-aura")
        try:
            self.nlp = pipeline("text-classification", model=model_path)
        except OSError as e:
            self.logging_service.error(f"Missing or unreadable local model files at {model_path}",
                user_id=0,
                extra={"error": str(e)}
            )
            self.nlp = None
        except ValueError as e:
            self.logging_service.error(f"ValueError loading model at {model_path} — likely missing files or offline-only mode",
                user_id=0,
                extra={"error": str(e)}
            )
            self.nlp = None
        except EntryNotFoundError as e:
            self.logging_service.error(f"EntryNotFoundError — model lookup failed for {model_path}",
                user_id=0,
                extra={"error": str(e)}
            )
            self.nlp = None
        else:
            self.logging_service.info(f"Loaded NLP model from {model_path}")
            return
