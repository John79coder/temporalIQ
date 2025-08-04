from typing import List, Optional
from sqlalchemy.orm import Session
from flask import current_app
from app.utils.exceptions import ServiceUnavailableError
from app.notion.smart_mapping.interfaces import IFieldDetector
from app.notion.smart_mapping.models import FieldMatch
from app.notion.smart_mapping.detector_registry import DetectorRegistry
import logging

class FieldDetectorAggregator(IFieldDetector):
    def __init__(self, registry: 'DetectorRegistry'):
        self.registry = registry

    def detect(self, fields: List[dict], rows: Optional[List[dict]] = None, db: Optional[Session] = None, user_id = None) -> List[FieldMatch]:
        """Run all registered detectors sequentially and aggregate results."""
        matches = []
        app = current_app._get_current_object()  # Capture the app instance

        def det_fn(det) -> List[FieldMatch]:
            with app.app_context():  # Use captured app
                return det.detect(fields, rows=rows, db=db, user_id=user_id)

        # Run sequentially to avoid thread/mock issues
        for det in self.registry.get_detectors():
            try:
                matches.extend(det_fn(det))
            except Exception as e:
                logging.error(f"Detector {det.__class__.__name__} failed: {str(e)}")

        return matches