# tests/logging/test_logging_system.py
import pytest
import json
import logging as python_logging
from datetime import datetime


def test_application_logger_standalone():
    """Test application logger without Flask app context"""
    from app.logging.services.application_logger import ApplicationLogger

    logger = ApplicationLogger()

    # Test different log levels
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")

    # Test error with exception
    try:
        raise ValueError("Test error")
    except ValueError as e:
        logger.error("Error message", exception=e)

    # Test operation context
    with logger.operation_context("test_operation", user_id=1) as op_id:
        logger.info("Inside operation", operation_id=op_id)

    assert True  # If we get here, logging worked


def test_audit_logger_with_app(app, test_user):
    """Test audit logging with Flask app context"""

    user, user_id = test_user

    with app.app_context():
        from app.logging.services.audit_logger import AuditLogger
        from app.logging.models.entities import AuditLog
        from app.extensions import db

        audit = AuditLogger()

        # Test authentication logging
        audit.log_authentication(
            event_type="login",
            user_id=user_id,
            email=user.email,
            success=True,
            metadata={"test": "value"}
        )

        # Verify it was persisted
        log = db.session.query(AuditLog).first()
        assert log is not None
        assert log.event_type == "login"
        assert log.success == True
        assert log.event_metadata["test"] == "value"


def test_event_tracker_with_app(app, test_user):
    """Test analytics event tracking with Flask app context"""
    with app.app_context():
        from app.analytics.services.event_tracker import EventTracker
        from app.analytics.models.entities import UserEvent
        from app.extensions import db

        tracker = EventTracker()

        # Track an event
        tracker.track(
            user_id=1,
            event_name="test_event",
            properties={"test": "value"}
        )

        # Flush to database
        tracker.flush()

        # Verify it was persisted
        event = db.session.query(UserEvent).first()
        assert event is not None
        assert event.event_name == "test_event"
        assert event.properties["test"] == "value"


def test_sensitive_data_filter():
    """Test that sensitive data is properly masked"""
    from app.logging.filters.sensitive_data_filter import SensitiveDataFilter

    filter = SensitiveDataFilter()

    # Create a mock log record with realistic key=value format
    record = python_logging.LogRecord(
        name="test",
        level=python_logging.INFO,
        pathname="",
        lineno=0,
        msg="password=password123 token=abc123def456",
        args=(),
        exc_info=None
    )

    # Apply filter
    filter.filter(record)

    # Check that sensitive data was masked
    assert "password123" not in record.msg
    assert "abc123def456" not in record.msg
    assert "****" in record.msg



def test_json_formatter():
    """Test JSON formatting of logs"""
    from app.logging.formatters.json_formatter import JSONFormatter

    formatter = JSONFormatter()

    # Create a mock log record
    record = python_logging.LogRecord(
        name="test",
        level=python_logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None
    )

    # Format the record
    formatted = formatter.format(record)

    # Check it's valid JSON
    parsed = json.loads(formatted)
    assert parsed["message"] == "Test message"
    assert parsed["level"] == "INFO"
    assert parsed["module"] == "test"


def test_console_formatter():
    """Test console formatting of logs"""
    from app.logging.formatters.console_formatter import ConsoleFormatter

    formatter = ConsoleFormatter(use_colors=False)  # Disable colors for testing

    # Create a mock log record
    record = python_logging.LogRecord(
        name="test",
        level=python_logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None
    )

    # Format the record
    formatted = formatter.format(record)

    # Check that it contains expected parts
    assert "Test message" in formatted
    assert "INFO" in formatted
    assert "test" in formatted


# Fixtures
@pytest.fixture(scope='function')
def app():
    """Create application for testing"""
    from app import create_app
    from config import TestingConfig
    from app.extensions import db

    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()