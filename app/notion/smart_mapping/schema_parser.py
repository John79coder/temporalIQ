# notion/smart_mapping/schema_parser.py
from typing import List

from app.notion.smart_mapping.interfaces import ISchemaParser


class SchemaParser(ISchemaParser):
    def normalize(self, notion_schema: dict) -> List[dict]:
        """Normalize Notion schema into a list of field dictionaries."""
        return [
            {"name": key, "type": val.get("type", "text")}
            for key, val in notion_schema.items()
        ]
