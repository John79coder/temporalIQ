from app.notion.smart_mapping.field_detectors.base import FieldDetector
from app.notion.smart_mapping.models import FieldMatch
from typing import List, Optional
from sqlalchemy.orm import Session

class KeywordMatcher(FieldDetector):
    keywords = {
        "title": [
            "title", "name", "task", "subject", "summary", "headline", "header"
        ],
        "due_date": [
            "due", "deadline", "date", "end", "finish", "due date", "completion date", "target"
        ],
        "start_date": [
            "start", "begin", "commence", "starting", "kickoff", "initiation", "begin date"
        ],
        "duration": [
            "duration", "time", "estimate", "effort", "length", "expected time", "workload", "planned time"
        ],
        "priority": [
            "priority", "importance", "urgency", "rank", "weight", "severity", "level"
        ],
        "status": [
            "status", "state", "stage", "phase", "progress", "condition"
        ],
        "assignee": [
            "assignee", "assigned to", "owner", "responsible", "user", "person", "delegate", "handler"
        ],
        "tags": [
            "tags", "labels", "categories", "group", "type", "classification", "marker"
        ],
        "created_at": [
            "created", "creation date", "date created", "timestamp", "added on", "entry date"
        ],
        "updated_at": [
            "updated", "modified", "last modified", "edited", "last update", "changed"
        ],
        "notes": [
            "notes", "description", "details", "comments", "remarks", "memo"
        ]
    }

    def detect(self, fields: list[dict], rows: Optional[List[dict]] = None, db: Optional[Session] = None, user_id: Optional[int] = None) -> list[FieldMatch]:
        matches = []
        for field in fields:
            name = field["name"].lower()
            for concept, keys in self.keywords.items():
                if any(k in name for k in keys):
                    matches.append(FieldMatch(
                        notion_field=field["name"],
                        matched_concept=concept,
                        confidence=0.7,
                        rationale="Keyword match"
                    ))
        return matches