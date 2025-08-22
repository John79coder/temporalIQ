import logging
from datetime import datetime, timezone
from typing import Dict, Any
from flask import g, has_request_context


class ConsoleFormatter(logging.Formatter):
    """
    Human-readable console formatter for development environments
    """

    # Color codes for different log levels
    COLORS = {
        'DEBUG': '\033[36m',  # Cyan
        'INFO': '\033[32m',  # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',  # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    BOLD = '\033[1m'

    def __init__(self, use_colors: bool = True, include_context: bool = True):
        super().__init__()
        self.use_colors = use_colors
        self.include_context = include_context

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console output"""

        # Build timestamp
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Get color if enabled
        if self.use_colors:
            level_color = self.COLORS.get(record.levelname, '')
            reset = self.RESET
            bold = self.BOLD
        else:
            level_color = reset = bold = ''

        # Build base message
        parts = [
            f"{bold}[{timestamp}]{reset}",
            f"{level_color}{bold}[{record.levelname:8}]{reset}",
            f"[{record.name}]",
        ]

        # Add context if available
        if self.include_context and has_request_context():
            context_parts = []

            if hasattr(g, 'request_id'):
                context_parts.append(f"req:{g.request_id[:8]}")

            if hasattr(g, 'current_user') and g.current_user:
                context_parts.append(f"user:{g.current_user.id}")

            if context_parts:
                parts.append(f"[{' '.join(context_parts)}]")

        # Add location info for debugging
        parts.append(f"{record.module}.{record.funcName}:{record.lineno}")

        # Add the actual message
        message = record.getMessage()
        parts.append(f"- {message}")

        # Format the complete line
        formatted = ' '.join(parts)

        # Add exception info if present
        if record.exc_info:
            formatted += '\n' + self.formatException(record.exc_info)
            if self.use_colors:
                # Make exceptions red
                formatted = formatted.replace('\n', f'\n{self.COLORS["ERROR"]}')
                formatted += reset

        # Add extra fields if present
        if hasattr(record, 'extra_fields') and record.extra_fields:
            extra_str = self._format_extra_fields(record.extra_fields)
            formatted += f"\n  {extra_str}"

        return formatted

    def _format_extra_fields(self, extra_fields: Dict[str, Any]) -> str:
        """Format extra fields for display"""
        items = []
        for key, value in extra_fields.items():
            if isinstance(value, (dict, list)):
                value = str(value)[:100] + '...' if len(str(value)) > 100 else str(value)
            items.append(f"{key}={value}")
        return ' | '.join(items)