# notion/smart_mapping/task_candidate.py
from typing import List, Optional
from collections import defaultdict
from zoneinfo import ZoneInfo

from sqlalchemy.orm.session import Session

from app.notion.models.entities import FieldMapping
from app.notion.smart_mapping.models import FieldMatch, TaskCandidateData
from app.utils.time_zone import TimeZone

from datetime import datetime

class TaskCandidateBuilder:
    def __init__(self, preferences_service):
        self.preferences_service = preferences_service

    def _parse_due_date(self, db: Session, due_date_str: str, user_id: int, issues: List[str]) -> Optional[datetime]:
        """Parse due_date_str and convert to UTC datetime, assuming user’s timezone if not UTC."""
        try:
            # Check if due_date_str is already in UTC
            if due_date_str.endswith('Z') or due_date_str.endswith('+00:00'):
                return TimeZone.parse_utc_datetime("due_date", due_date_str)
            # Parse as datetime with timezone info
            due_date = datetime.fromisoformat(due_date_str)

            user_prefs = self.preferences_service.get_preferences(db, user_id)

            user_tz = user_prefs.time_zone if user_prefs and user_prefs.time_zone else "UTC"
            # Ensure datetime is localized to user's timezone if naive
            if due_date.tzinfo is None:
                due_date = due_date.replace(tzinfo=ZoneInfo(user_tz))
            utc_datetime = TimeZone.to_utc(due_date, user_tz)
            return utc_datetime
        except ValueError as e:
            issues.append(f"Invalid due_date format: {due_date_str}")
            return None
        except Exception as e:
            issues.append(f"Failed to parse due_date: {str(e)}")
            return None

    def build_from_row(self, db: Session, matches: List[FieldMatch], row: dict, mapping: FieldMapping, user_id: int = None,
                       notion_db_id: str = None) -> TaskCandidateData:
        issues = []
        alternatives = {}
        title = None
        due_date = None
        duration = None
        priority = None
        status = None
        tags = None

        if mapping:
            properties = row.get("properties", {})
            if mapping.title_field in properties:
                title_data = properties[mapping.title_field].get("title", [{}])[0].get("plain_text")
                title = title_data if title_data else "Untitled"
            else:
                issues.append(f"Missing title field: {mapping.title_field}")
            if mapping.due_date_field in properties:
                due_date = properties[mapping.due_date_field].get("date", {}).get("start")
            elif mapping.due_date_field:
                issues.append(f"Missing due_date field: {mapping.due_date_field}")
            if mapping.duration_field in properties:
                duration = properties[mapping.duration_field].get("number")
            elif mapping.duration_field:
                issues.append(f"Missing duration field: {mapping.duration_field}")
            confidence = 0.9 if not issues else 0.5
        else:
            if not matches:  # Handle empty matches gracefully
                issues.append("No field matches provided, using default values")
                confidence = 0.5
            else:
                grouped = defaultdict(list)
                for m in sorted(matches, key=lambda x: x.confidence, reverse=True):
                    grouped[m.matched_concept].append(m)
                for concept, group in grouped.items():
                    if len(group) > 1:
                        issues.append(f"Ambiguous {concept}: {[m.notion_field for m in group]}")
                        alternatives[concept] = [m.notion_field for m in group[1:]]
                    top = group[0] if group else None
                    if top and top.confidence < 0.7:
                        issues.append(f"Low confidence for {concept}: {top.confidence:.2f}")
                fields = {concept: group[0].notion_field if group else None for concept, group in grouped.items()}
                properties = row.get("properties", {})
                if "title" in fields and fields["title"] in properties:
                    title = properties[fields["title"]].get("title", [{}])[0].get("plain_text", "Untitled")
                if "due_date" in fields and fields["due_date"] in properties:
                    due_date = properties[fields["due_date"]].get("date", {}).get("start")
                if "duration" in fields and fields["duration"] in properties:
                    duration = properties[fields["duration"]].get("number")
                if "priority" in fields and fields["priority"] in properties:
                    priority = properties[fields["priority"]].get("select", {}).get("name")
                if "status" in fields and fields["status"] in properties:
                    status = properties[fields["status"]].get("select", {}).get("name")
                if "tags" in fields and fields["tags"] in properties:
                    tags = [t.get("name") for t in properties[fields["tags"]].get("multi_select", [])]
                for concept in ["title", "due_date", "duration", "priority", "status", "tags"]:
                    if concept not in fields:
                        issues.append(f"Missing field for {concept}")
                confidence = sum(m.confidence for m in matches) / len(matches) if matches else 0.5

        return TaskCandidateData(
            user_id=user_id or (mapping.user_id if mapping else 0),
            notion_db_id=notion_db_id or (mapping.notion_db_id if mapping else ""),
            title=title,
            due_date=due_date,
            duration=duration,
            confidence=confidence,
            issues=issues,
            priority=priority,
            status=status,
            tags=tags,
            alternatives=alternatives or None,
            page_id=""
        )