from typing import List, Optional
from sqlalchemy.orm import Session
from flask import current_app
from app.utils.exceptions import ServiceUnavailableError
from app.notion.smart_mapping.interfaces import IFieldDetector
from app.notion.smart_mapping.models import FieldMatch
from app.notion.smart_mapping.detector_registry import DetectorRegistry
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

class FieldDetectorAggregator(IFieldDetector):
    def __init__(self, registry: 'DetectorRegistry'):
        self.registry = registry
        self.max_workers = 5

    def detect(self, fields: List[dict], rows: Optional[List[dict]] = None, db: Optional[Session] = None, user_id = None) -> List[FieldMatch]:
        """Run all registered detectors in parallel and aggregate results."""
        matches = []
        app = current_app._get_current_object()  # Capture the app instance before threading

        def det_fn(det) -> List[FieldMatch]:
            with app.app_context():  # Use captured app
                return det.detect(fields, rows=rows, db=db, user_id=user_id)

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = [ex.submit(det_fn, det) for det in self.registry.get_detectors()]
            for future in as_completed(futures):
                try:
                    matches.extend(future.result())
                except Exception as e:
                    logging.error(f"Parallel detector execution failed: {str(e)}")
                    # Fallback to sequential execution
                    for det in self.registry.get_detectors():
                        try:
                            with app.app_context():  # Use captured app
                                matches.extend(det.detect(fields, rows=rows, db=db, user_id=user_id))
                        except (ValueError, TypeError, ServiceUnavailableError) as se:
                            logging.error(f"Sequential detector {det.__class__.__name__} failed: {str(se)}")
                    break
        return matches