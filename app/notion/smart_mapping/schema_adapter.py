# notion/smart_mapping/schema_adapter.py
from typing import List

class SchemaAdapter:
    def normalize(self, notion_schema: dict) -> List[dict]:
        return [
            {"name": key, "type": val.get("type", "text")}
            for key, val in notion_schema.items()
        ]
