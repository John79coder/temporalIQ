import re
from datetime import datetime, timedelta
from typing import List

from pydantic import BaseModel, model_serializer, field_validator, ConfigDict

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


class TimeBlockIn(BaseModel):
    start: datetime
    end: datetime
    task_id: int | None = None

    @field_validator("start", "end")
    def validate_z_format(cls, v: datetime) -> datetime:
        """Ensure datetime is in Z-format (UTC)."""
        if not v.tzinfo or v.tzinfo.utcoffset(v) != timedelta(0):
            raise ValueError("Datetime must be in UTC (Z-format)")
        return v

    @field_validator("end")
    def validate_end_after_start(cls, v, values):
        if "start" in values.data and v <= values.data["start"]:
            raise ValueError("end must be after start")
        return v


class SchedulePreviewIn(BaseModel):
    user_id: int
    notion_db_id: str
    calendar_id: str
    start_date: datetime
    end_date: datetime
    earliest_time: str
    latest_time: str

    @field_validator("start_date", "end_date")
    def validate_z_format(cls, v: datetime) -> datetime:
        """Ensure datetime is in Z-format (UTC)."""
        if not v.tzinfo or v.tzinfo.utcoffset(v) != timedelta(0):
            raise ValueError("Datetime must be in UTC (Z-format)")
        return v

    @field_validator("earliest_time", "latest_time")
    def validate_time_format(cls, v: str) -> str:
        """Validate HH:MM format for time strings."""
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("Time format must be HH:MM")
        try:
            hour, minute = map(int, v.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid hours or minutes")
        except ValueError:
            raise ValueError("Invalid time format")
        return v


class ScheduleConfirmIn(BaseModel):
    user_id: int
    calendar_id: str
    time_blocks: List[TimeBlockIn]


class TimeBlockOut(BaseOutModel):
    start: datetime
    end: datetime
    task_id: int | None = None


class SchedulePreviewOut(BaseOutModel):
    time_blocks: List[TimeBlockOut]
