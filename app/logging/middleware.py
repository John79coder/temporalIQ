# app/logging/middleware.py
import time
import uuid
from typing import Callable


class LoggingMiddleware:
    """
    WSGI middleware for comprehensive request/response logging
    """

    def __init__(self, app: Callable, logger):
        self.app = app
        self.logger = logger

    def __call__(self, environ, start_response):
        """
        Log request and response details with timing
        """

        # Generate request ID
        request_id = str(uuid.uuid4())
        environ['REQUEST_ID'] = request_id

        # Record start time (monotonic to avoid patches/drift)
        start_time = time.perf_counter()

        # Log request
        self._log_request(environ, request_id)

        # Capture response
        def custom_start_response(status, headers, exc_info=None):
            # Compute duration in ms and normalize to a float
            try:
                duration_ms = float((time.perf_counter() - start_time) * 1000)
            except (TypeError, ValueError):
                duration_ms = None

            # Log response
            self._log_response(
                environ,
                status,
                headers,
                duration_ms,
                request_id,
                exc_info
            )

            # Add custom headers
            headers.append(('X-Request-ID', request_id))
            if isinstance(duration_ms, (int, float)):
                headers.append(('X-Response-Time-ms', str(int(duration_ms))))

            return start_response(status, headers, exc_info)

        try:
            return self.app(environ, custom_start_response)
        except Exception as e:
            # Compute duration safely for the error path too
            try:
                duration_ms = float((time.perf_counter() - start_time) * 1000)
            except (TypeError, ValueError):
                duration_ms = None

            self.logger.error(
                "Request failed with exception",
                exception=e,
                request_id=request_id,
                duration_ms=duration_ms,
                path=environ.get('PATH_INFO'),
                method=environ.get('REQUEST_METHOD')
            )
            raise

    def _log_request(self, environ: dict, request_id: str):
        """Log incoming request details"""

        self.logger.info(
            "Request received",
            request_id=request_id,
            method=environ.get('REQUEST_METHOD'),
            path=environ.get('PATH_INFO'),
            query_string=environ.get('QUERY_STRING'),
            remote_addr=environ.get('REMOTE_ADDR'),
            user_agent=environ.get('HTTP_USER_AGENT'),
            content_length=environ.get('CONTENT_LENGTH'),
            content_type=environ.get('CONTENT_TYPE')
        )

    def _log_response(
            self,
            environ: dict,
            status: str,
            headers: list,
            duration_ms: float,
            request_id: str,
            exc_info=None
    ):
        """Log outgoing response details"""

        status_code = int(status.split(' ')[0])
        level = 'error' if status_code >= 500 else 'warning' if status_code >= 400 else 'info'

        log_method = getattr(self.logger, level)

        log_method(
            "Request completed",
            request_id=request_id,
            status_code=status_code,
            duration_ms=duration_ms,
            path=environ.get('PATH_INFO'),
            method=environ.get('REQUEST_METHOD')
        )

        # Log slow requests (only if the duration is numeric)
        if isinstance(duration_ms, (int, float)) and duration_ms > 1000:  # More than 1 second
            self.logger.warning(
                "Slow request detected",
                request_id=request_id,
                duration_ms=duration_ms,
                path=environ.get('PATH_INFO')
            )
