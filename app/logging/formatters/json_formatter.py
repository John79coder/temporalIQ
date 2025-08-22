# app/logging/formatter/json_formatter.py
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Dict, Any
from flask import request, g, has_request_context


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter that includes contextual information
    and properly handles exceptions
    """

    def __init__(self, include_stacktrace: bool = True):
        super().__init__()
        self.include_stacktrace = include_stacktrace

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with comprehensive metadata"""

        log_obj = self._build_log_object(record)

        # Add request context if available
        if has_request_context():
            log_obj.update(self._get_request_context())

        # Add user context if available
        log_obj.update(self._get_user_context())

        # Add exception info if present
        if record.exc_info and self.include_stacktrace:
            log_obj["exception"] = self._format_exception(record.exc_info)

        # Add custom fields from extra
        if hasattr(record, 'extra_fields'):
            log_obj["extra"] = record.extra_fields

        return json.dumps(log_obj, default=str, ensure_ascii=False)

    def _build_log_object(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Build the base log object"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "process_id": record.process,
            "thread_id": record.thread,
            "thread_name": record.threadName,
        }

    def _get_request_context(self) -> Dict[str, Any]:
        """Extract request context information"""
        context = {}
        try:
            context.update({
                "request_id": getattr(g, 'request_id', None),
                "method": request.method,
                "path": request.path,
                "remote_addr": request.remote_addr,
                "user_agent": request.headers.get('User-Agent'),
                "referrer": request.headers.get('Referer'),
                "correlation_id": request.headers.get('X-Correlation-ID'),
            })

            # Add query parameters (be careful with sensitive data)
            if request.args:
                context["query_params"] = dict(request.args)

        except Exception:
            pass  # Silently ignore if request context is not available

        return {"request": context} if context else {}

    def _get_user_context(self) -> Dict[str, Any]:
        """Extract user context information"""
        context = {}
        try:
            if hasattr(g, 'current_user') and g.current_user:
                context.update({
                    "user_id": g.current_user.id,
                    "user_email": g.current_user.email,
                    "user_plan": getattr(g.current_user, 'plan_tier', None),
                })
        except Exception:
            pass

        return {"user": context} if context else {}

    def _format_exception(self, exc_info) -> Dict[str, Any]:
        """Format exception information as structured data"""
        exc_type, exc_value, exc_traceback = exc_info

        return {
            "type": exc_type.__name__ if exc_type else None,
            "message": str(exc_value) if exc_value else None,
            "stacktrace": traceback.format_exception(exc_type, exc_value, exc_traceback)
        }