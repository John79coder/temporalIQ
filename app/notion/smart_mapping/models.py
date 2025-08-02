# notion/smart_mapping/models.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime


class FieldMatch(BaseModel):
    notion_field: str
    matched_concept: str
    confidence: float
    rationale: Optional[str] = None


class TaskCandidateData(BaseModel):
    user_id: int
    notion_db_id: Optional[str] = None
    page_id: Optional[str] = None
    title: Optional[str] = None
    due_date: Optional[datetime] = None
    duration: Optional[int] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)  # Example with constraints
    issues: List[str] = Field(default_factory=list)
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    alternatives: Optional[Dict[str, List[str]]] = Field(default_factory=dict)
    source_block_ids: Optional[List[str]] = None
