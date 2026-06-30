# app/utils/exceptions.py
from typing import Tuple
from typing import Type

from flask.wrappers import Response


class AppError(Exception):
    """Base class for application-specific exceptions."""
    pass


class AuthError(AppError):
    """Raised for authentication-related errors."""
    pass


class NotionError(AppError):
    """Raised for Notion API errors or integration errors."""
    pass


class CalendarError(AppError):
    """Raised for iCloud calendar or CalDAV errors."""
    pass


class DataValidationError(AppError):
    """Raised for input-validation errors."""
    pass


class ServiceUnavailableError(AppError):
    """Raised for external service errors or system errors."""
    pass


class DatabaseError(AppError):
    """Raised for database-related errors."""
    pass

class InternalError(AppError):
    """Raised for unexpected/uncategorized internal errors (generic catch-all 500s)."""
    pass

def format_error_response(error: Exception, status_code: int) -> Tuple[dict, int]:
    """
    Format an error into RFC 7807 JSON.
    """
    msg = str(error).strip()
    return {
        "type": "about:blank",
        "title": error.__class__.__name__,
        "status": status_code,
        "detail": msg
    }, status_code


def wrap_external_error(error: Exception, custom_type: Type[AppError], message: str) -> AppError:
    """Wrap an external exception in a custom application exception."""
    return custom_type(f"{message}: {str(error)}")


def make_handled_error_response(app_error: Type[AppError], error_message: str | None, status_code: int) -> Response:
    error_response, status_code = format_error_response(app_error(error_message), status_code)
    from flask import jsonify
    from flask.helpers import make_response
    return make_response(jsonify(error_response), status_code)
