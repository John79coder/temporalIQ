# app/notion/models/schemas.py
from pydantic import BaseModel, ConfigDict, Field, field_validator, HttpUrl
from datetime import datetime
from typing import Optional, List
from enum import Enum
from app.utils.time_zone import TimeZone

class BaseOutModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: TimeZone.serialize_datetime}
    )

class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Status(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

class NotionTokenIn(BaseModel):
    user_id: int = Field(ge=1, description="User ID, must be positive")
    code: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$", description="OAuth authorization code")
    redirect_uri: HttpUrl = Field(description="Redirect URI for OAuth flow")

    @field_validator("code")
    def validate_code(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Code cannot be empty or whitespace")
        return v

class NotionTokenOut(BaseOutModel):
    user_id: int = Field(ge=1, description="User ID, must be positive")
    access_token: str = Field(min_length=1, description="Notion API access token")
    expires_at: datetime = Field(description="Token expiration timestamp")
    workspace_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9-]+$", description="Notion workspace ID")
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("access_token")
    def validate_access_token(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Access token cannot be empty or whitespace")
        return v

class DatabaseOut(BaseOutModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9-]+$", description="Notion database ID")
    title: str = Field(min_length=1, description="Database title")

    @field_validator("title")
    def validate_title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title cannot be empty or whitespace")
        return v

class FieldMappingIn(BaseModel):
    user_id: int = Field(ge=1, description="User ID, must be positive")
    notion_db_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9-]+$", description="Notion database ID")
    title_field: str = Field(min_length=1, description="Field name for task title")
    due_date_field: Optional[str] = Field(None, min_length=1, description="Field name for due date")
    duration_field: Optional[str] = Field(None, min_length=1, description="Field name for duration")

    @field_validator("title_field", "due_date_field", "duration_field")
    def validate_field_names(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Field name cannot be empty or whitespace")
        return v

class FieldMappingOut(BaseOutModel):
    id: int = Field(ge=1, description="Mapping ID, must be positive")
    user_id: int = Field(ge=1, description="User ID, must be positive")
    notion_db_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9-]+$", description="Notion database ID")
    title_field: str = Field(min_length=1, description="Field name for task title")
    due_date_field: Optional[str] = Field(None, min_length=1, description="Field name for due date")
    duration_field: Optional[str] = Field(None, min_length=1, description="Field name for duration")
    created_at: datetime = Field(description="Mapping creation timestamp")
    updated_at: Optional[datetime] = None

    @field_validator("title_field", "due_date_field", "duration_field")
    def validate_field_names(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Field name cannot be empty or whitespace")
        return v

class TaskCandidateOut(BaseOutModel):
    title: str = Field(min_length=1, description="Task title")
    due_date: Optional[datetime] = Field(
        None,
        description="Due date in ISO 8601 UTC format"
    )
    duration: Optional[int] = Field(None, ge=1, le=1440, description="Duration in minutes (1-1440)")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    issues: List[str] = Field(min_items=0, description="List of mapping issues")
    priority: Optional[Priority] = Field(None, description="Task priority (high, medium, low)")
    status: Optional[Status] = Field(None, description="Task status (todo, in_progress, done)")
    tags: Optional[List[str]] = Field(None, min_items=0, description="List of task tags")
    created_at: datetime
    updated_at: Optional[datetime] = None
    page_id: Optional[str] = None
    database_id: Optional[str] = None

    @field_validator("title")
    def validate_title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title cannot be empty or whitespace")
        return v

    @field_validator("issues")
    def validate_issues(cls, v: List[str]) -> List[str]:
        for issue in v:
            if not issue.strip():
                raise ValueError("Issue descriptions cannot be empty or whitespace")
        return v

    @field_validator("tags")
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            for tag in v:
                if not tag.strip():
                    raise ValueError("Tags cannot be empty or whitespace")
        return v

# NEW: Added PartialCandidate for extractor partials
class PartialCandidate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[datetime] = None
    description: Optional[str] = None
    duration: Optional[int] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    confidence: float = 0.5
    urgency: float = 0.5

    # NEW: Positional metadata to support stitching/adjacency
    block_id: Optional[str] = None         # Notion block ID the partial was extracted from
    block_index: Optional[int] = None      # Index of the block within the section
    span_index: Optional[int] = None       # Index of this partial within the block
    extraction_order: Optional[int] = None # Global sequence number of extraction