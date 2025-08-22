# app/logging/filters/sensitive_data_filter.py
import re
import logging
from typing import List
from app.logging.config import LogConfig


class SensitiveDataFilter(logging.Filter):
    """
    Filter to mask sensitive data in log messages
    """

    def __init__(self, patterns: List[str] = None):
        super().__init__()
        config = LogConfig()
        self.patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in (patterns or config.sensitive_patterns)
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Mask sensitive data in the log message"""

        # Mask in the main message
        record.msg = self._mask_sensitive_data(str(record.msg))

        # Mask in arguments
        if record.args:
            record.args = tuple(
                self._mask_sensitive_data(str(arg)) for arg in record.args
            )

        # Mask in extra fields
        if hasattr(record, 'extra_fields'):
            record.extra_fields = self._mask_dict_values(record.extra_fields)

        return True

    def _mask_sensitive_data(self, text: str) -> str:
        """Replace sensitive patterns with the masked version"""
        for pattern in self.patterns:
            text = pattern.sub(lambda m: SensitiveDataFilter._mask_match(m), text)
        return text

    @staticmethod
    def _mask_match(match) -> str:
        """Mask a regex match, preserving some characters for debugging"""
        sensitive_value = match.group(1) if match.lastindex else match.group(0)
        if len(sensitive_value) <= 4:
            return "****"
        else:
            # Show the first 2 and last 2 characters
            return f"{sensitive_value[:2]}{'*' * (len(sensitive_value) - 4)}{sensitive_value[-2:]}"

    def _mask_dict_values(self, data: dict) -> dict:
        """Recursively mask sensitive values in a dictionary"""
        if not isinstance(data, dict):
            return data

        masked = {}
        sensitive_keys = {'password', 'token', 'secret', 'api_key', 'access_token',
                          'refresh_token', 'credit_card', 'ssn'}

        for key, value in data.items():
            if any(sensitive_key in key.lower() for sensitive_key in sensitive_keys):
                masked[key] = "****REDACTED****"
            elif isinstance(value, dict):
                masked[key] = self._mask_dict_values(value)
            elif isinstance(value, str):
                masked[key] = self._mask_sensitive_data(value)
            else:
                masked[key] = value

        return masked