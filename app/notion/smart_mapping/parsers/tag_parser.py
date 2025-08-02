import re
from typing import Optional, List

from app.notion.smart_mapping.parsers.field_value_parser import FieldValueParser


class TagParser(FieldValueParser):
    TAG_PATTERN = r"#(\w+)"
    INLINE_LABEL_PATTERN = r"\b(?:tag|category|project):\s*([A-Za-z0-9_]+)\b"

    def parse(self, text: str) -> Optional[List[str]]:
        tags = re.findall(self.TAG_PATTERN, text)
        inline = re.findall(self.INLINE_LABEL_PATTERN, text, re.IGNORECASE)
        combined = list({tag.lower() for tag in tags + inline})
        return combined or None
