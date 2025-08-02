# app/user_preferences/models/schemas.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from config import Config
from app.utils.time_zone import TimeZone

class BaseOutModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: TimeZone.serialize_datetime}
    )

class PreferencesCreate(BaseModel):
    user_id: int
    default_notion_db: str | None = None
    block_size_minutes: int = Config.DEFAULT_BLOCK_MINUTES
    allow_weekends: bool = Config.INCLUDE_WEEKENDS
    max_blocks_per_day: int = Config.DEFAULT_MAX_BLOCKS_PER_DAY
    work_hours: float = Config.DEFAULT_WORK_HOURS_PER_DAY
    time_zone: Optional[str] = Field(None, description="User's time zone (e.g., America/New_York)")

class PreferencesOut(BaseOutModel):
    id: int
    user_id: int
    default_notion_db: Optional[str]
    block_size_minutes: int
    allow_weekends: bool
    max_blocks_per_day: int
    work_hours: float
    created_at: datetime
    updated_at: Optional[datetime] = None
    time_zone: Optional[str] = None