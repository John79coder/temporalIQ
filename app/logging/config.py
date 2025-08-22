# app/logging/config.py
import os
from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass, field
import logging  # Import standard logging module


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def to_python_level(self):
        """Convert to Python logging level"""
        return getattr(logging, self.value)


class LoggerName(str, Enum):
    APPLICATION = "app"
    AUDIT = "audit"
    PERFORMANCE = "performance"
    SECURITY = "security"
    INTEGRATION = "integration"
    BUSINESS = "business"


@dataclass
class LogConfig:
    """Centralized logging configuration"""

    # Environment-based settings
    environment: str = os.getenv("FLASK_ENV", "development")

    # Log levels per environment
    log_levels: Dict[str, str] = field(default_factory=lambda: {
        "development": "DEBUG",
        "test": "INFO",
        "staging": "INFO",
        "production": "WARNING"
    })

    # File paths
    log_dir: str = os.getenv("LOG_DIR", "./logs")  # Changed to relative path for Windows
    app_log_file: str = "application.log"
    audit_log_file: str = "audit.log"
    performance_log_file: str = "performance.log"

    # Rotation settings
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 10
    rotation_when: str = "midnight"
    rotation_interval: int = 1

    # Performance settings
    async_logging: bool = False  # Disabled for Windows compatibility
    buffer_size: int = 1024

    # Feature flags
    enable_json_logging: bool = environment != "development"
    enable_console_logging: bool = True
    enable_file_logging: bool = True
    enable_remote_logging: bool = environment == "production"

    # Remote logging settings
    remote_logging_endpoint: str = os.getenv("LOG_AGGREGATOR_ENDPOINT", "")
    remote_logging_api_key: str = os.getenv("LOG_AGGREGATOR_API_KEY", "")

    # Sensitive data patterns to mask
    sensitive_patterns: list = field(default_factory=lambda: [
        r"password[\"']?\s*[:=]\s*[\"']?([^\"'\s]+)",
        r"token[\"']?\s*[:=]\s*[\"']?([^\"'\s]+)",
        r"api[_-]?key[\"']?\s*[:=]\s*[\"']?([^\"'\s]+)",
        r"secret[\"']?\s*[:=]\s*[\"']?([^\"'\s]+)",
        r"ssn[\"']?\s*[:=]\s*[\"']?(\d{3}-\d{2}-\d{4})",
        r"credit[_-]?card[\"']?\s*[:=]\s*[\"']?(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})"
    ])

    @property
    def current_log_level(self) -> str:
        """Return log level as string, not enum"""
        return self.log_levels.get(self.environment, "INFO")