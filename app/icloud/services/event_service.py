# app/icloud/services/event_service.py
import logging
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.icloud.models.entities import CalendarSelection
from app.icloud.models.schemas import CalendarEvent, CalendarMetadata, EventWriteRequest
from app.icloud.repositories.repository import ICloudRepository
from app.icloud.services.interfaces import ICalDAVEventService, ICalDAVClientManager
from app.utils.caching import ICacheService
from app.utils.exceptions import CalendarError, DatabaseError, wrap_external_error


class CalDAVEventService(ICalDAVEventService):
    def __init__(self, caching_service: ICacheService, repo: ICloudRepository, client_manager: 'ICalDAVClientManager'):
        self.caching_service = caching_service
        self.repo = repo
        self.client_manager = client_manager

    def list_user_calendars(self, user_id: int, db: Session) -> List[CalendarMetadata]:
        cache_key = f"icloud:calendars:{user_id}"
        cached_calendars = self.caching_service.get(cache_key)
        if cached_calendars:
            return [CalendarMetadata(**cal) for cal in cached_calendars]

        client = self.client_manager.get_caldav_client_for_user(db, user_id)

        calendars = client.list_calendars()

        self.caching_service.set(
            cache_key,
            [cal.model_dump() for cal in calendars],
            timeout=604800  # 7 days
        )

        return calendars

    def fetch_user_events(self, user_id: int, db: Session, calendar_id: str, start: datetime, end: datetime) -> List[
        CalendarEvent]:
        cache_key = f"icloud:events:{user_id}:{calendar_id}:{start.isoformat()}:{end.isoformat()}"
        cached_events = self.caching_service.get(cache_key)
        if cached_events:
            return [CalendarEvent(**event) for event in cached_events]

        client = self.client_manager.get_caldav_client_for_user(db, user_id)

        events = client.fetch_events(calendar_id, start, end)

        self.caching_service.set(
            cache_key,
            [event.model_dump() for event in events],
            timeout=3600  # 1 hour
        )

        return events

    def write_scheduled_event(self, user_id: int, db: Session, calendar_id: str, event: EventWriteRequest) -> str:
        client = self.client_manager.get_caldav_client_for_user(db, user_id)
        uid = client.write_event(calendar_id, event)
        self.caching_service.delete(f"icloud:events:{user_id}:{calendar_id}")
        self.caching_service.delete(f"icloud:time_blocks:{user_id}:{calendar_id}:*")
        return uid

    def write_scheduled_blocks(self, user_id: int, db: Session, calendar_id: str,
                               events: List[EventWriteRequest]) -> None:
        written_uids = []
        try:
            for event in events:
                uid = self.write_scheduled_event(user_id, db, calendar_id, event)
                written_uids.append(uid)
        except Exception as e:
            client = self.client_manager.get_caldav_client_for_user(db, user_id)
            for uid in written_uids:
                try:
                    client.delete_event(calendar_id, uid)
                    logging.info(f"Rollback: Deleted event {uid} from calendar {calendar_id}")
                except Exception as del_e:
                    logging.error(f"Rollback failed for event {uid}: {str(del_e)}")
            raise wrap_external_error(e, CalendarError, "Failed to write scheduled blocks")

    def save_user_calendar_selection(self, db: Session, selection: 'CalendarSelection') -> None:
        try:
            self.repo.save_calendar_selection(db, selection)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to save calendar selection")
        self.caching_service.delete(f"icloud:calendars:{selection.user_id}")

    def get_user_default_calendar(self, db: Session, user_id: int) -> CalendarSelection:
        cache_key = f"icloud:default_calendar:{user_id}"
        cached_calendar = self.caching_service.get(cache_key)
        if cached_calendar:
            return CalendarSelection(**cached_calendar)
        try:
            calendar = self.repo.get_default_calendar_for_user(db, user_id)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve default calendar")
        if not calendar:
            raise CalendarError("No default calendar selected for user")
        self.caching_service.set(
            cache_key,
            calendar.__dict__,
            timeout=86400  # 1 day
        )
        return calendar
