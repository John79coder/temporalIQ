# tests/icloud/test_icloud_services.py
from app.utils.exceptions import CalendarError
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from app.icloud.services.client_manager import CalDAVClientManager
from app.icloud.services.event_service import CalDAVEventService
from app.icloud.services.time_block_service import TimeBlockService
from app.icloud.models.schemas import CalendarMetadata, TimeBlock
from app.icloud.repositories.repository import ICloudRepository
from app.utils.encryption import Encryptor
from app.auth.models.entities import User


class PicklableMock:
    def __init__(self, mock):
        self.mock = mock

    def __getattr__(self, name):
        return getattr(self.mock, name)

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        self.mock = Mock()


@pytest.fixture
def icloud_repo():
    return Mock(spec=ICloudRepository)

@pytest.fixture
def client_manager(caching_service, icloud_repo):
    return CalDAVClientManager(caching_service, icloud_repo)

@pytest.fixture
def event_service(caching_service, icloud_repo, client_manager):
    return CalDAVEventService(caching_service, icloud_repo, client_manager)

@pytest.fixture
def time_block_service(caching_service, client_manager):
    return TimeBlockService(caching_service, client_manager)


@patch('app.icloud.services.client_manager.CalDAVClientDecorator')
@patch('app.icloud.services.client_manager.CalDAVClient')
@patch('app.utils.time_zone.TimeZone.serialize_datetime')
def test_client_manager_get_caldav_client(
    mock_serialize_datetime,
    mock_caldav_client,
    mock_decorator,
    client_manager,
    icloud_repo,
    caching_service
):
    db = Mock()
    user_id = 1
    encryptor = Encryptor()

    valid_encrypted_password = encryptor.encrypt("valid_app_password")
    connection_created_at = datetime(2025, 7, 12, 0, 0, tzinfo=timezone.utc)

    icloud_repo.get_icloud_connection_by_user.return_value = Mock(
        encrypted_app_password=valid_encrypted_password,
        created_at=connection_created_at,
        updated_at=None  # Explicitly set to None
    )

    mock_user = Mock(spec=User)
    mock_user.email = "test@example.com"
    db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_client_instance = PicklableMock(Mock())
    mock_decorator.return_value = mock_client_instance  # ensure decorator returns mock

    mock_caldav_client.return_value = mock_client_instance

    mock_serialize_datetime.return_value = "2025-07-12T00:00:00Z"

    client = client_manager.get_caldav_client_for_user(db, user_id)

    connection_cache = caching_service.get(f"icloud:connection:{user_id}", decrypt=True)

    assert connection_cache == {
        'encrypted_app_password': valid_encrypted_password,
        'created_at': "2025-07-12T00:00:00Z",
        'updated_at': None  # Updated assertion to match
    }

    client_cache = caching_service.get(f"icloud:client:{user_id}")

    assert isinstance(client_cache, PicklableMock)
    assert client is mock_client_instance

@patch('app.icloud.services.client_manager.CalDAVClientManager.get_caldav_client_for_user')
def test_event_service_list_calendars(mock_get_caldav_client, event_service, caching_service):

    db = Mock()
    user_id = 1

    mock_client = Mock()

    calendars = [
        CalendarMetadata(calendar_id="cal1", display_name="Calendar 1", timezone="UTC")
    ]

    mock_client.list_calendars.return_value = calendars

    mock_get_caldav_client.return_value = mock_client


    result = event_service.list_user_calendars(user_id, db)

    assert len(result) == 1
    assert result[0].calendar_id == "cal1"
    assert result[0].display_name == "Calendar 1"
    assert result[0].timezone == "UTC"

    mock_get_caldav_client.assert_called_once_with(db, user_id)

    cached_calendars = caching_service.get(f"icloud:calendars:{user_id}")

    assert cached_calendars == [cal.model_dump() for cal in calendars]


@patch('app.icloud.services.client_manager.CalDAVClientManager.get_caldav_client_for_user')
def test_time_block_service_get_available_blocks(mock_get_caldav_client, time_block_service, client_manager):

    db = Mock()
    user_id = 1
    calendar_id = "cal1"
    start_date = datetime(2025, 7, 12)
    end_date = datetime(2025, 7, 12)

    mock_client = Mock()
    mock_client.fetch_events.return_value = []

    mock_get_caldav_client.return_value = mock_client

    blocks = time_block_service.get_available_time_blocks(user_id, db, calendar_id, start_date, end_date, "09:00", "17:00")

    assert isinstance(blocks, list)
    assert len(blocks) > 0
    assert all(isinstance(block, TimeBlock) for block in blocks)



from datetime import datetime, timezone

@patch("caldav.DAVClient.__init__", side_effect=Exception("Network failure"))
@patch("app.icloud.repositories.repository.ICloudRepository.get_icloud_connection_by_user")
def test_icloud_network_failure_recovery(mock_get_connection, mock_caldav_init, db_session, caching_service):
    encryptor = Encryptor()
    valid_encrypted = encryptor.encrypt("dummy_password")
    mock_connection = MagicMock(encrypted_app_password=valid_encrypted)
    mock_connection.created_at = datetime.now(timezone.utc)  # ✅ Fix
    mock_connection.updated_at = None
    mock_get_connection.return_value = mock_connection
    manager = CalDAVClientManager(caching_service, ICloudRepository())
    with pytest.raises(CalendarError, match="Failed to initialize CalDAV client"):
        manager.get_caldav_client_for_user(db_session, 1)