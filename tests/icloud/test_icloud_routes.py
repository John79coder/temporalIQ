# tests/icloud/test_routes.py
import uuid
from unittest.mock import patch, MagicMock
from flask import g
from app.icloud.models.entities import iCloudConnection
from app.auth.models.entities import User
from datetime import datetime, timezone
from app.utils.encryption import Encryptor

def test_connect_icloud_success(authorized_client, db_session, app, test_user, caching_service):
    _, user_id = test_user
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        email = f"test_icloud_{uuid.uuid4().hex}@example.com"
        response = authorized_client.post("/icloud/connect", json={
            "app_password": "test-password"
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 200
        assert response.json["message"] == "iCloud connection saved."
        conn = db_session.query(iCloudConnection).filter_by(user_id=user_id).first()
        assert conn is not None
        assert conn.encrypted_app_password is not None

def test_connect_icloud_invalid_data(authorized_client, db_session, app, test_user):
    _, user_id = test_user
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        response = authorized_client.post("/icloud/connect", json={
            "app_password": ""
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 400
        assert "error" in response.json["detail"]

@patch('app.utils.caching.InMemoryCacheService.set')
@patch('app.utils.encryption.Encryptor.decrypt')
@patch('caldav.DAVClient')
@patch('app.auth.models.entities.User')
def test_list_calendars_success(mock_user, mock_dav_client, mock_decrypt, mock_cache_set, authorized_client, db_session, app, test_user):
    user, user_id = test_user
    mock_decrypt.return_value = 'valid_app_password'
    mock_cache_set.return_value = None
    mock_user_instance = MagicMock()
    mock_user_instance.email = user.email
    mock_user.query.filter.return_value.first.return_value = mock_user_instance
    mock_dav_instance = MagicMock()
    mock_dav_client.return_value = mock_dav_instance
    mock_calendar = MagicMock()
    mock_calendar.url = "https://caldav.icloud.com/cal1/"
    mock_calendar.get_property.return_value = "Test Calendar"
    mock_dav_instance.principal.return_value.calendars.return_value = [mock_calendar]
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        db_session.add(iCloudConnection(user_id=user_id, encrypted_app_password="encrypted"))
        db_session.commit()
        response = authorized_client.get(
            "/icloud/calendars",
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )
        assert response.status_code == 200
        assert len(response.json["calendars"]) == 1
        assert response.json["calendars"][0]["calendar_id"] == "cal1"
        assert response.json["calendars"][0]["display_name"] == "Test Calendar"
        assert response.json["calendars"][0]["timezone"] == "UTC"
        mock_dav_client.assert_called_once_with(
            url="https://caldav.icloud.com",
            username=user.email,
            password='valid_app_password'
        )
        mock_dav_instance.principal.return_value.calendars.assert_called_once()

def test_list_calendars_no_connection(authorized_client, db_session, app, test_user):
    _, user_id = test_user
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        response = authorized_client.get("/icloud/calendars", headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 500
        assert "No iCloud connection" in response.json["detail"]

@patch('app.utils.caching.InMemoryCacheService.set')
@patch('app.utils.encryption.Encryptor.decrypt')
@patch('caldav.DAVClient')
@patch('app.auth.models.entities.User')
@patch('app.icloud.client.caldav_client_decorator.CalDAVClientDecorator._extract_calendar_timezone')
def test_get_events_success(mock_get_calendar, mock_user, mock_dav_client, mock_decrypt, mock_cache_set, authorized_client, db_session, app, test_user):
    _, user_id = test_user
    mock_get_calendar.return_value = "UTC"
    mock_decrypt.return_value = 'valid_app_password'
    mock_cache_set.return_value = None
    mock_user_instance = MagicMock()
    mock_user_instance.email = "test@example.com"
    mock_user.query.filter.return_value.first.return_value = mock_user_instance
    mock_dav_instance = MagicMock()
    mock_dav_client.return_value = mock_dav_instance
    start_time = datetime(2023, 10, 10, 10, 0, tzinfo=timezone.utc)
    end_time = datetime(2023, 10, 10, 11, 0, tzinfo=timezone.utc)
    mock_calendar = MagicMock()
    mock_calendar.date_search.return_value = [
        MagicMock(
            icalendar_component={
                "DTSTART": MagicMock(dt=start_time),
                "DTEND": MagicMock(dt=end_time),
                "SUMMARY": "Event",
                "UID": "event1"
            }
        )
    ]
    mock_dav_instance.principal.return_value.calendar.return_value = mock_calendar
    start_param = start_time.replace(hour=0, minute=0).isoformat().replace("+00:00", "Z")
    end_param = start_time.replace(day=start_time.day + 1, hour=0, minute=0).isoformat().replace("+00:00", "Z")
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        db_session.add(iCloudConnection(user_id=user_id, encrypted_app_password="encrypted"))
        db_session.commit()
        response = authorized_client.get(
            f"/icloud/events?calendar_id=cal1&start={start_param}&end={end_param}",
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )
        assert response.status_code == 200
        assert len(response.json["events"]) == 1
        assert response.json["events"][0]["summary"] == "Event"

@patch('app.utils.caching.InMemoryCacheService.set')
@patch('app.utils.encryption.Encryptor.decrypt')
@patch('caldav.DAVClient')
@patch('app.auth.models.entities.User')
def test_get_events_invalid_parameters(mock_user, mock_dav_client, mock_decrypt, mock_cache_set, authorized_client, db_session, app, test_user):
    user, user_id = test_user
    mock_decrypt.return_value = 'valid_app_password'
    mock_cache_set.return_value = None
    mock_user_instance = MagicMock()
    mock_user_instance.email = user.email
    mock_user.query.filter.return_value.first.return_value = mock_user_instance
    mock_dav_instance = MagicMock()
    mock_dav_client.return_value = mock_dav_instance
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        response = authorized_client.get("/icloud/events", headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 400
        assert "Missing required parameters" in response.json["detail"]

@patch('app.utils.caching.InMemoryCacheService.set')
@patch('app.utils.encryption.Encryptor.decrypt')
@patch('caldav.DAVClient')
@patch('app.auth.models.entities.User')
def test_create_event_success(mock_user, mock_dav_client, mock_decrypt, mock_cache_set, authorized_client, db_session, app, test_user):
    _, user_id = test_user
    mock_decrypt.return_value = 'valid_app_password'
    mock_cache_set.return_value = None
    mock_user_instance = MagicMock()
    mock_user_instance.email = "test@example.com"
    mock_user.query.filter.return_value.first.return_value = mock_user_instance
    mock_dav_instance = MagicMock()
    mock_dav_client.return_value = mock_dav_instance
    mock_calendar = MagicMock()
    mock_calendar.add_event.return_value = None
    mock_dav_instance.principal.return_value.calendar.return_value = mock_calendar
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        db_session.add(iCloudConnection(user_id=user_id, encrypted_app_password="encrypted"))
        db_session.commit()
        event = {
            "calendar_id": "cal1",
            "event": {
                "title": "Test Event",
                "start": "2023-10-10T10:00:00Z",
                "end": "2023-10-10T11:00:00Z"
            }
        }
        response = authorized_client.post("/icloud/events", json=event, headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 200
        assert response.json["message"] == "Event written to iCloud."

def test_create_event_no_connection(authorized_client, db_session, app, test_user):
    _, user_id = test_user
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        event = {
            "calendar_id": "cal1",
            "event": {
                "title": "Test Event",
                "start": "2023-10-10T10:00:00Z",
                "end": "2023-10-10T11:00:00Z"
            }
        }
        response = authorized_client.post("/icloud/events", json=event, headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 500
        assert isinstance(response.json, dict)
        assert "No iCloud connection" in response.json["detail"]

@patch('app.utils.caching.InMemoryCacheService.set')
@patch('app.utils.encryption.Encryptor.encrypt')
def test_update_icloud_connection_success(mock_encrypt, mock_cache_set, authorized_client, db_session, app, test_user):
    _, user_id = test_user
    mock_encrypt.return_value = 'new-encrypted'
    mock_cache_set.return_value = None
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        db_session.add(iCloudConnection(user_id=user_id, encrypted_app_password="old-encrypted"))
        db_session.commit()
        response = authorized_client.post("/icloud/update", json={
            "app_password": "new-password"
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 200
        assert response.json["message"] == "iCloud connection updated."
        conn = db_session.query(iCloudConnection).filter_by(user_id=user_id).first()
        assert conn.encrypted_app_password != "old-encrypted"

def test_update_icloud_connection_no_connection(authorized_client, db_session, app, test_user):
    _, user_id = test_user
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        response = authorized_client.post("/icloud/update", json={
            "app_password": "new-password"
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 500
        assert "No iCloud connection" in response.json["detail"]

@patch('app.utils.caching.InMemoryCacheService.set')
@patch('app.utils.encryption.Encryptor.decrypt')
@patch('caldav.DAVClient')
@patch('app.auth.models.entities.User')
def test_get_available_time_blocks_success(mock_user, mock_dav_client, mock_decrypt, mock_cache_set, authorized_client, db_session, app, test_user):
    _, user_id = test_user
    mock_decrypt.return_value = 'valid_app_password'
    mock_cache_set.return_value = None
    mock_user_instance = MagicMock()
    mock_user_instance.email = "test@example.com"
    mock_user.query.filter.return_value.first.return_value = mock_user_instance
    mock_dav_instance = MagicMock()
    mock_dav_client.return_value = mock_dav_instance
    mock_calendar = MagicMock()
    mock_calendar.date_search.return_value = []
    mock_dav_instance.principal.return_value.calendar.return_value = mock_calendar
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        db_session.add(iCloudConnection(user_id=user_id, encrypted_app_password="encrypted"))
        db_session.commit()
        response = authorized_client.get(
            "/icloud/available?calendar_id=cal1&start_date=2023-10-10T00:00:00Z&end_date=2023-10-11T00:00:00Z&earliest_time=09:00&latest_time=17:00",
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )
        assert response.status_code == 200
        assert len(response.json["time_blocks"]) > 0

@patch('app.utils.caching.InMemoryCacheService.set')
@patch('app.utils.encryption.Encryptor.decrypt')
@patch('caldav.DAVClient')
@patch('app.auth.models.entities.User')
def test_get_available_time_blocks_invalid_time(mock_user, mock_dav_client, mock_decrypt, mock_cache_set, authorized_client, db_session, app, test_user):
    user, user_id = test_user
    mock_decrypt.return_value = 'valid_app_password'
    mock_cache_set.return_value = None
    mock_user_instance = MagicMock()
    mock_user_instance.email = user.email
    mock_user.query.filter.return_value.first.return_value = mock_user_instance
    mock_dav_instance = MagicMock()
    mock_dav_client.return_value = mock_dav_instance
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        response = authorized_client.get(
            "/icloud/available?calendar_id=cal1&start_date=2023-10-10T00:00:00Z&end_date=2023-10-11T00:00:00Z&earliest_time=17:00&latest_time=09:00",
            headers={"X-CSRF-Token": authorized_client.csrf_token}
        )
        assert response.status_code == 400
        assert "earliest_time must be before latest_time" in response.json["detail"]

@patch('app.utils.caching.InMemoryCacheService.set')
@patch('caldav.DAVClient')
@patch('app.auth.models.entities.User')
def test_schedule_blocks_success(mock_user, mock_dav_client, mock_cache_set, authorized_client, db_session, app, test_user):
    _, user_id = test_user
    encryptor = Encryptor()
    valid_encrypted_password = encryptor.encrypt("valid_app_password")
    mock_cache_set.return_value = None
    mock_user_instance = MagicMock()
    mock_user_instance.email = "test@example.com"
    mock_user.query.filter.return_value.first.return_value = mock_user_instance
    mock_dav_instance = MagicMock()
    mock_dav_client.return_value = mock_dav_instance
    mock_calendar = MagicMock()
    mock_calendar.add_event.return_value = None
    mock_dav_instance.principal.return_value.calendar.return_value = mock_calendar
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        db_session.add(iCloudConnection(user_id=user_id, encrypted_app_password=valid_encrypted_password))
        db_session.commit()
        events = [{
            "title": "Test Event",
            "start": "2023-10-10T10:00:00Z",
            "end": "2023-10-10T11:00:00Z"
        }]
        response = authorized_client.post("/icloud/schedule", json={
            "calendar_id": "cal1",
            "events": events
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 200
        assert response.json["message"] == "Events written to iCloud."

def test_schedule_blocks_invalid_events(authorized_client, db_session, app, test_user):
    _, user_id = test_user
    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)
        db_session.add(iCloudConnection(user_id=user_id, encrypted_app_password="encrypted"))
        db_session.commit()
        response = authorized_client.post("/icloud/schedule", json={
            "calendar_id": "cal1",
            "events": [{"title": "", "start": "2023-10-10T10:00:00Z", "end": "2023-10-10T11:00:00Z"}]
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 400
        assert "String should have at least 1 character" in response.json["detail"]