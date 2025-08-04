from datetime import datetime
from typing import Optional
from pydantic import BaseModel, model_serializer, Field, ConfigDict
from config import Config
from app.utils.time_zone import TimeZone

class BaseOutModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @model_serializer(mode='wrap')
    def serialize_model(self, handler) -> dict:
        data = handler(self)
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = TimeZone.serialize_datetime(value)
        return data

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