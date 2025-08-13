# app/icloud/client/caldav_client.py
import logging
import uuid
from datetime import datetime
from typing import List
from xml.etree.ElementTree import ParseError

import caldav
from caldav.elements import dav
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.icloud.client.interfaces import ICalendarClient
from app.icloud.models.schemas import CalendarEvent, CalendarMetadata, EventWriteRequest
from app.utils.exceptions import CalendarError, wrap_external_error
from app.utils.time_zone import TimeZone


class CalDAVClient(ICalendarClient):
    def __init__(self, user_email: str, app_password: str):
        self.app_password = app_password
        self.base_url = "https://caldav.icloud.com"
        try:
            self.client = caldav.DAVClient(
                url=self.base_url,
                username=user_email,
                password=app_password
            )
            self.principal = self.client.principal()
        except Exception as e:
            raise wrap_external_error(e, CalendarError, "Failed to initialize CalDAV client")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(caldav.error.DAVError))
    def list_calendars(self) -> List[CalendarMetadata]:
        try:
            calendars = self.principal.calendars()
            logging.info("Successfully listed iCloud calendars")
            return [
                CalendarMetadata(
                    calendar_id=cal.url.rstrip("/").split("/")[-1],
                    display_name=self._extract_display_name(cal.get_property(dav.DisplayName())),
                    timezone="UTC",
                )
                for cal in calendars
            ]
        except caldav.error.DAVError as e:
            logging.error(f"Failed to list iCloud calendars: {str(e)}")
            raise wrap_external_error(e, CalendarError, "Failed to list calendars")

    @staticmethod
    def _extract_display_name(value):
        try:
            if hasattr(value, "text") and value.text:
                return value.text
            return str(value) if value else "Untitled"
        except (AttributeError, TypeError, ParseError) as e:
            logging.error(f"Failed to extract calendar display name: {str(e)}")
            return "Untitled"

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(caldav.error.DAVError))
    def fetch_events(self, calendar_id: str, start: datetime, end: datetime) -> List[CalendarEvent]:
        try:
            calendar = self.principal.calendar(cal_id=calendar_id)
            events = calendar.date_search(start, end)
            logging.info(f"Successfully fetched events for calendar {calendar_id}")
            return [
                CalendarEvent(
                    start=event.icalendar_component["DTSTART"].dt,
                    end=event.icalendar_component["DTEND"].dt,
                    summary=event.icalendar_component.get("SUMMARY", ""),
                    uid=event.icalendar_component.get("UID", "")
                )
                for event in events
            ]
        except caldav.error.DAVError as e:
            logging.error(f"Failed to fetch events for calendar {calendar_id}: {str(e)}")
            raise wrap_external_error(e, CalendarError, "Failed to fetch events")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(caldav.error.DAVError))
    def write_event(self, calendar_id: str, event: EventWriteRequest) -> str:
        try:
            calendar = self.principal.calendar(cal_id=calendar_id)
            uid = event.uid or str(uuid.uuid4())
            ical_event = caldav.Event(
                calendar.client,
                data=f"""
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:{uid}
DTSTART:{TimeZone.serialize_datetime(event.start)}
DTEND:{TimeZone.serialize_datetime(event.end)}
SUMMARY:{event.title}
DESCRIPTION:{event.notes or ""}
END:VEVENT
END:VCALENDAR
"""
            )
            calendar.add_event(ical_event)
            logging.info(f"Successfully wrote event {uid} to calendar {calendar_id}")
            return uid
        except caldav.error.DAVError as e:
            logging.error(f"Failed to write event to calendar {calendar_id}: {str(e)}")
            raise wrap_external_error(e, CalendarError, "Failed to write event")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(caldav.error.DAVError))
    def delete_event(self, calendar_id: str, uid: str) -> None:
        try:
            calendar = self.principal.calendar(cal_id=calendar_id)
            event = calendar.event_by_uid(uid)
            if event:
                event.delete()
                logging.info(f"Successfully deleted event {uid} from calendar {calendar_id}")
            else:
                logging.warning(f"Event {uid} not found in calendar {calendar_id}")
        except caldav.error.NotFoundError:
            logging.warning(f"Event {uid} not found for deletion in calendar {calendar_id}")
        except caldav.error.DAVError as e:
            logging.error(f"Failed to delete event {uid} from calendar {calendar_id}: {str(e)}")
            raise wrap_external_error(e, CalendarError, "Failed to delete event")
