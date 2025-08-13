import re
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator, model_serializer, ConfigDict

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


class CalendarEvent(BaseOutModel):
    start: datetime
    end: datetime
    summary: Optional[str]
    uid: Optional[str]


class CalendarMetadata(BaseOutModel):
    calendar_id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    timezone: Optional[str]
    is_writable: bool = True


class EventWriteRequest(BaseModel):
    title: str = Field(..., min_length=1)
    start: datetime
    end: datetime
    notes: Optional[str] = None
    uid: Optional[str] = None

    @field_validator("start", "end", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        if isinstance(v, str):
            return TimeZone.parse_utc_datetime("datetime", v)
        return v


class iCloudConnectIn(BaseModel):
    app_password: str = Field(..., min_length=1)


class iCloudConnectOut(BaseOutModel):
    message: str


class CalendarListOut(BaseOutModel):
    calendars: List[CalendarMetadata]


class EventListOut(BaseOutModel):
    events: List[CalendarEvent]


class EventCreateIn(BaseModel):
    calendar_id: str = Field(..., min_length=1)
    event: EventWriteRequest


class EventCreateOut(BaseOutModel):
    message: str


class TimeBlock(BaseOutModel):
    start: datetime
    end: datetime


class AvailableTimeBlocksOut(BaseOutModel):
    time_blocks: List[TimeBlock]


class AvailableTimeBlocksIn(BaseModel):
    calendar_id: str = Field(..., min_length=1)
    start_date: datetime
    end_date: datetime
    earliest_time: str
    latest_time: str

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_datetime(cls, v):
        if isinstance(v, str):
            return TimeZone.parse_utc_datetime("datetime", v)
        return v

    @field_validator("earliest_time", "latest_time")
    def validate_time_format(cls, v):
        if not isinstance(v, str) or not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", v):
            raise ValueError("Time must be in HH:MM format (e.g., 09:00 to 23:59)")
        return v


class ScheduleBlocksIn(BaseModel):
    calendar_id: str = Field(..., min_length=1)
    events: List[EventWriteRequest]


class ScheduleBlocksOut(BaseOutModel):
    message: str
