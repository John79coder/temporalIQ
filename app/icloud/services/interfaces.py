# app/icloud/services/interfaces.py
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.icloud.models.schemas import CalendarEvent, CalendarMetadata, EventWriteRequest, TimeBlock


class ICalDAVClientManager(ABC):
    @abstractmethod
    def get_caldav_client_for_user(self, db: Session, user_id: int) -> 'ICalendarClient':
        pass


class ICalDAVEventService(ABC):
    @abstractmethod
    def list_user_calendars(self, user_id: int, db: Session) -> List[CalendarMetadata]:
        pass

    @abstractmethod
    def fetch_user_events(self, user_id: int, db: Session, calendar_id: str, start: datetime, end: datetime) -> List[
        CalendarEvent]:
        pass

    @abstractmethod
    def write_scheduled_event(self, user_id: int, db: Session, calendar_id: str, event: EventWriteRequest) -> None:
        pass

    @abstractmethod
    def save_user_calendar_selection(self, db: Session, selection: 'CalendarSelection') -> None:
        pass

    @abstractmethod
    def get_user_default_calendar(self, db: Session, user_id: int) -> 'CalendarSelection':
        pass


class ITimeBlockService(ABC):
    @abstractmethod
    def get_available_time_blocks(
            self,
            user_id: int,
            db: Session,
            calendar_id: str,
            start_date: datetime,
            end_date: datetime,
            earliest_time: str,
            latest_time: str
    ) -> List[TimeBlock]:
        pass
