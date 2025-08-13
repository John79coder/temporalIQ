# app/icloud/client/interfaces.py
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from app.icloud.models.schemas import CalendarEvent, CalendarMetadata, EventWriteRequest


class ICalendarClient(ABC):
    @abstractmethod
    def list_calendars(self) -> List[CalendarMetadata]:
        pass

    @abstractmethod
    def fetch_events(self, calendar_id: str, start: datetime, end: datetime) -> List[CalendarEvent]:
        pass

    @abstractmethod
    def write_event(self, calendar_id: str, event: EventWriteRequest) -> str:
        pass

    @abstractmethod
    def delete_event(self, calendar_id: str, uid: str) -> None:
        pass
