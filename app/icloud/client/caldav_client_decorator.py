# app/icloud/client/caldav_client_decorator.py
from datetime import datetime
from typing import List
from icalendar.cal import Calendar
from app.icloud.client.interfaces import ICalendarClient
from app.icloud.models.schemas import CalendarEvent, CalendarMetadata, EventWriteRequest
from app.utils.time_zone import TimeZone
from icalendar import Calendar as iCalendar, Timezone as iTimezone
import zoneinfo
import logging

class CalDAVClientDecorator(ICalendarClient):
    def __init__(self, client: ICalendarClient):
        self.client = client

    def list_calendars(self) -> List[CalendarMetadata]:
        return self.client.list_calendars()

    def fetch_events(self, calendar_id: str, start: datetime, end: datetime) -> List[CalendarEvent]:
        # noinspection PyUnresolvedReferences
        calendar = self.client.principal.calendar(cal_id=calendar_id)
        timezone = self._extract_calendar_timezone(calendar)
        events = self.client.fetch_events(calendar_id, start, end)
        return [
            CalendarEvent(
                start=TimeZone.to_utc(event.start, timezone),
                end=TimeZone.to_utc(event.end, timezone),
                summary=event.summary,
                uid=event.uid
            )
            for event in events
        ]

    def write_event(self, calendar_id: str, event: EventWriteRequest) -> str:
        return self.client.write_event(calendar_id, event)

    def delete_event(self, calendar_id: str, uid: str) -> None:
        self.client.delete_event(calendar_id, uid)

    @staticmethod
    def _extract_calendar_timezone(calendar: Calendar) -> str:
        try:
            # noinspection PyUnresolvedReferences
            raw_calendar = calendar.vobject_instance or calendar
            serialized_calendar = iCalendar.from_ical(raw_calendar.serialize())
            timezone_component = next((c for c in serialized_calendar.walk() if isinstance(c, iTimezone)), None)
            timezone_id = timezone_component.get('TZID') if timezone_component else None
            if timezone_id and str(timezone_id) in zoneinfo.available_timezones():
                return str(timezone_id)
            logging.warning(f"Invalid or missing timezone ID: {timezone_id}, defaulting to UTC")
            return "UTC"
        except (AttributeError, TypeError, ValueError) as e:
            logging.error(f"Failed to extract calendar timezone: {str(e)}")
            return "UTC"