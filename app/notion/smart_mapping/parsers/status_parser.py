import re
from typing import Optional

from app.notion.smart_mapping.parsers.field_value_parser import FieldValueParser


class StatusParser(FieldValueParser):
    STATUS_PATTERN = (
        r"\b(done|completed|finished|closed|todo|to do|in progress|pending)\b"
    )
    CHECKBOX_PATTERN = r"[✅✔]\s*(?:done)?"

    def parse(self, text: str) -> Optional[str]:
        m = re.search(self.STATUS_PATTERN, text, re.IGNORECASE)
        if m:
            return m.group(1).lower().replace(" ", "_")
        m2 = re.search(self.CHECKBOX_PATTERN, text)
        if m2:
            return "done"
        return None
