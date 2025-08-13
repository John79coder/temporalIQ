# tests/contract/test_contract.py
from datetime import datetime, timezone
from unittest.mock import patch

from app.icloud.client.caldav_client import CalDAVClient
from app.icloud.models.schemas import EventWriteRequest


@patch('caldav.DAVClient')
def test_icloud_mock_event_format(mock_dav):
    mock_inst = mock_dav.return_value
    mock_inst.principal.return_value.calendar.return_value.add_event = Mock()
    client = CalDAVClient('u', 'p')
    event = EventWriteRequest(title="Test", start=datetime(2025, 7, 19, 10, 0, tzinfo=timezone.utc),
                              end=datetime(2025, 7, 19, 11, 0, tzinfo=timezone.utc), notes="Note")
    client.write_event("cal1", event)
    ical_data = mock_inst.principal.return_value.calendar.return_value.add_event.call_args[0][0].data
    assert "BEGIN:VCALENDAR" in ical_data
    assert "SUMMARY:Test" in ical_data
    assert "DESCRIPTION:Note" in ical_data
    assert "DTSTART:2025-07-19T10:00:00Z" in ical_data
    assert "DTEND:2025-07-19T11:00:00Z" in ical_data


from unittest.mock import Mock
import requests


@patch("requests.Session.post")
def test_notion_mock_invalid_token(mock_post, authorized_client, caching_service):
    # Create a mock response that raises HTTPError on .raise_for_status()
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.HTTPError(response=Mock(status=401))
    mock_post.return_value = mock_response

    caching_service.print_cache()

    # Call endpoint
    response = authorized_client.post(
        "/notion/connect",
        json={"user_id": 1, "code": "code", "redirect_uri": "http://localhost"},
        headers={"X-CSRF-Token": authorized_client.csrf_token}
    )

    # Check result
    assert response.status_code == 500
    assert "401" in response.json["detail"]
