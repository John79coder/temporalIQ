import logging
import uuid
import os
from typing import Optional, Dict, Any
from functools import wraps
from contextlib import contextmanager
from datetime import datetime
from flask import g, request
from app.logging.config import LogConfig, LoggerName
from app.logging.formatters.json_formatter import JSONFormatter
from app.logging.formatters.console_formatter import ConsoleFormatter
from app.logging.filters.sensitive_data_filter import SensitiveDataFilter
from app.logging.handlers.rotating_handler import SmartRotatingFileHandler


class ApplicationLogger:
    """
    Main application logger with support for multiple handlers,
    structured logging, and performance tracking
    """

    _instance = None
    _loggers: Dict[str, logging.Logger] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.config = LogConfig()
        self._setup_loggers()
        self._initialized = True

    def _setup_loggers(self):
        """Initialize all logger types with appropriate handlers"""

        # Setup application logger
        self._setup_logger(
            LoggerName.APPLICATION,
            self.config.app_log_file,
            self.config.current_log_level
        )

        # Setup audit logger (always logs everything)
        self._setup_logger(
            LoggerName.AUDIT,
            self.config.audit_log_file,
            "INFO"
        )

        # Setup performance logger
        self._setup_logger(
            LoggerName.PERFORMANCE,
            self.config.performance_log_file,
            "INFO"
        )

    def _setup_logger(self, name: str, filename: str, level: str):
        """Setup individual logger with handlers"""

        logger = logging.getLogger(name)

        # Convert string level to Python logging level
        if isinstance(level, str):
            python_level = getattr(logging, level.upper())
        else:
            python_level = logging.INFO  # Default fallback

        logger.setLevel(python_level)
        logger.propagate = False

        # Clear existing handlers
        logger.handlers = []

        # Create log directory if it doesn't exist
        os.makedirs(self.config.log_dir, exist_ok=True)

        # Add sensitive data filter
        sensitive_filter = SensitiveDataFilter()

        # Console handler for development
        if self.config.enable_console_logging:
            console_handler = logging.StreamHandler()
            if self.config.environment == "development":
                console_handler.setFormatter(ConsoleFormatter())
            else:
                console_handler.setFormatter(JSONFormatter())
            console_handler.addFilter(sensitive_filter)
            logger.addHandler(console_handler)

        # File handler with rotation
        if self.config.enable_file_logging:
            log_file_path = os.path.join(self.config.log_dir, filename)
            file_handler = SmartRotatingFileHandler(
                filename=log_file_path,
                max_bytes=self.config.max_bytes,
                backup_count=self.config.backup_count,
                compress=False  # Disable compression for Windows compatibility
            )
            file_handler.setFormatter(JSONFormatter())
            file_handler.addFilter(sensitive_filter)
            logger.addHandler(file_handler)

        self._loggers[name] = logger

    def get_logger(self, name: str = LoggerName.APPLICATION) -> logging.Logger:
        """Get a specific logger instance"""
        # Convert enum to string if necessary
        if hasattr(name, 'value'):
            name = name.value
        return self._loggers.get(name, logging.getLogger(name))

    # Convenience methods for different log levels
    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exception: Optional[Exception] = None, **kwargs):
        self._log(logging.ERROR, message, exc_info=exception, **kwargs)

    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs):
        self._log(logging.CRITICAL, message, exc_info=exception, **kwargs)

    def _log(self, level: int, message: str, exc_info=None, **kwargs):
        """Internal logging method with context enrichment"""

        logger = self.get_logger()

        # Create extra fields
        extra_fields = {}

        # Add standard fields if available
        try:
            if hasattr(g, 'request_id'):
                extra_fields['request_id'] = g.request_id
        except RuntimeError:
            # Outside of request context
            pass

        # Add custom fields from kwargs
        for key, value in kwargs.items():
            if key not in ['exc_info', 'stack_info', 'extra']:
                extra_fields[key] = value

        # Create log record with extra fields
        logger.log(
            level,
            message,
            exc_info=exc_info,
            extra={'extra_fields': extra_fields}
        )

    @contextmanager
    def operation_context(self, operation_name: str, **kwargs):
        """
        Context manager for tracking operation duration and status

        Usage:
            with logger.operation_context("database_query", query_type="select"):
                # perform operation
        """

        start_time = datetime.utcnow()
        operation_id = str(uuid.uuid4())

        self.info(
            f"Operation started: {operation_name}",
            operation_id=operation_id,
            operation_name=operation_name,
            **kwargs
        )

        try:
            yield operation_id

            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            self.info(
                f"Operation completed: {operation_name}",
                operation_id=operation_id,
                operation_name=operation_name,
                duration_ms=duration_ms,
                status="success",
                **kwargs
            )

        except Exception as e:
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            self.error(
                f"Operation failed: {operation_name}",
                exception=e,
                operation_id=operation_id,
                operation_name=operation_name,
                duration_ms=duration_ms,
                status="error",
                error_type=type(e).__name__,
                **kwargs
            )
            raise

    def log_request(self):
        """Log incoming request details"""

        try:
            if not request:
                return

            self.info(
                "Request received",
                method=request.method,
                path=request.path,
                remote_addr=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
            )
        except RuntimeError:
            # Outside of request context
            pass

    def log_response(self, response):
        """Log outgoing response details"""

        try:
            self.info(
                "Response sent",
                status_code=response.status_code,
                content_length=response.content_length,
            )
        except Exception:
            pass

        return response