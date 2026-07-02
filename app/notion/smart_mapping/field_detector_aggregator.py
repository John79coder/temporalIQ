# app/notion/smart_mapping/field_detector_aggregator.py
from typing import List, Optional

from flask import current_app
from sqlalchemy.orm import Session

from app.notion.smart_mapping.detector_registry import DetectorRegistry
from app.notion.smart_mapping.interfaces import IFieldDetector
from app.notion.smart_mapping.models import FieldMatch


class FieldDetectorAggregator(IFieldDetector):
    def __init__(self, registry: DetectorRegistry):
        self.registry = registry

    def detect(
        self,
        fields: List[dict],
        rows: Optional[List[dict]] = None,
        db: Optional[Session] = None,
        user_id: Optional[int] = None,
    ) -> List[FieldMatch]:
        """
        Run all registered detectors sequentially and aggregate results.

        Detectors may log via their own LoggingService; this aggregator
        only coordinates them and does not use the global logger.
        """
        matches: List[FieldMatch] = []
        app = current_app._get_current_object()  # Capture the app instance

        def det_fn(det) -> List[FieldMatch]:
            with app.app_context():
                return det.detect(fields, rows=rows, db=db, user_id=user_id)

        for det in self.registry.get_detectors():
            try:
                matches.extend(det_fn(det))
            except Exception as e:
                # Use the registry's LoggingService if available, but do not re-log
                # via the global logger. Detectors are responsible for detailed logs.
                if hasattr(self.registry, "logging_service") and self.registry.logging_service:
                    self.registry.logging_service.error(
                        "Field detector failed",
                        user_id=user_id,
                        extra={
                            "detector": det.__class__.__name__,
                            "error": str(e),
                        },
                    )
                # Swallow detector-specific errors to allow other detectors to run.
                continue

        return matches
