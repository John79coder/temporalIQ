import re
from datetime import datetime, timedelta
from typing import Optional

from app.notion.smart_mapping.parsers.field_value_parser import FieldValueParser


class DueDateParser(FieldValueParser):
    DATE_PATTERNS = [
        # Specific absolute dates
        r"\b(?:due|by|on)\s+(?P<date>(?:\w{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?))",
        # Relative references
        r"\b(?:due|by)?\s*(?P<relative>today|tomorrow|next\s+\w+|in\s+\d+\s+days?)\b"
    ]

    def parse(self, text: str) -> Optional[str]:
        now = datetime.now()
        for pat in self.DATE_PATTERNS:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                if match.group("relative"):
                    return self._resolve_relative(match.group("relative").lower(), now)
                return match.group("date")
        return None

    def _resolve_relative(self, label: str, now: datetime) -> str:
        if label == "today":
            return now.strftime("%Y-%m-%d")
        if label == "tomorrow":
            return (now + timedelta(days=1)).strftime("%Y-%m-%d")
        m = re.match(r"in\s+(\d+)\s+days?", label)
        if m:
            return (now + timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
        m2 = re.match(r"next\s+(\w+)", label)
        if m2:
            import calendar
            wd = m2.group(1)
            try:
                weekday = list(calendar.day_name).index(wd.capitalize())
                days_ahead = (weekday - now.weekday() + 7) % 7 or 7
                return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            except:
                return label
        return label
