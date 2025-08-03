# app/utils/logging_service.py
from typing import Any, Dict, Optional
from app.utils.time_zone import TimeZone
import logging
import os

from config import Config


class _SafeExtraFilter(logging.Filter):
    def filter(self, record):
        record.user_id = getattr(record, 'user_id', '-')
        record.task_id = getattr(record, 'task_id', '-')
        record.timestamp = getattr(record, 'timestamp', '-')
        return True

class LoggingService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            log_file = Config.LOG_FILE_PATH
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s - user_id=%(user_id)s task_id=%(task_id)s timestamp=%(timestamp)s'
            ))
            file_handler.addFilter(_SafeExtraFilter())  # ✅ Ensures all fields exist
            self.logger.addHandler(file_handler)
            self.logger.addHandler(logging.StreamHandler())
        self.logger.debug("LoggingService initialized")

    def error(self, message: str, user_id: Optional[int] = None, task_id: Optional[int] = None, extra: Optional[Dict[str, Any]] = None):
        extra = extra or {}
        if user_id is not None:
            extra['user_id'] = user_id
        if task_id is not None:
            extra['task_id'] = task_id
        extra['timestamp'] = TimeZone.utc_now().isoformat()
        self.logger.error(message, extra=extra)
        for handler in self.logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.flush()

    def info(self, message: str, user_id: Optional[int] = None, task_id: Optional[int] = None, extra: Optional[Dict[str, Any]] = None):
        extra = extra or {}
        if user_id is not None:
            extra['user_id'] = user_id
        if task_id is not None:
            extra['task_id'] = task_id
        extra['timestamp'] = TimeZone.utc_now().isoformat()
        self.logger.info(message, extra=extra)
        for handler in self.logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.flush()
