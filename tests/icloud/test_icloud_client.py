# tests/icloud/test_client.py
from datetime import datetime
from unittest.mock import Mock

import pytest

from app.icloud.client.interfaces import ICalendarClient
from app.icloud.models.schemas import CalendarMetadata, CalendarEvent


@pytest.fixture
def caldav_client():
    return Mock(spec=ICalendarClient)


def test_caldav_client_list_calendars(caldav_client):
    caldav_client.list_calendars.return_value = [
        CalendarMetadata(calendar_id="cal1", display_name="Calendar 1", timezone="UTC")]

    calendars = caldav_client.list_calendars()

    assert len(calendars) == 1
    assert calendars[0].calendar_id == "cal1"


def test_caldav_client_fetch_events(caldav_client):
    caldav_client.fetch_events.return_value = [
        CalendarEvent(start=datetime.now(), end=datetime.now(), summary="Event", uid="uid1")]

    events = caldav_client.fetch_events("cal1", datetime.now(), datetime.now())

    assert len(events) == 1
    assert events[0].uid == "uid1"
