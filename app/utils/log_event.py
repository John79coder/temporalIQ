import json
import logging

from flask import g, has_request_context, request


def get_correlation_id() -> str | None:
    if not has_request_context():
        return None
    return getattr(g, "correlation_id", None) or request.headers.get("X-Correlation-ID")


def log_event(logger: logging.Logger, level: int, event: str, **fields) -> None:
    payload = {
        "event": event,
        "correlation_id": get_correlation_id(),
        **fields,
    }
    logger.log(level, json.dumps(payload))