import re
from typing import Optional

from app.notion.smart_mapping.parsers.field_value_parser import FieldValueParser


class DurationParser(FieldValueParser):
    DURATION_PATTERN = (
        r"\b(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>hours?|hrs?|h|minutes?|mins?|m)\b|"
        r"\bhalf an hour\b"
    )

    def parse(self, text: str) -> Optional[str]:
        m = re.search(self.DURATION_PATTERN, text, re.IGNORECASE)
        if m:
            if m.group("value"):
                return f"{m.group('value')} {m.group('unit')}"
            return "0.5 hours"
        return None
