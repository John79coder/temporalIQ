# app/icloud/services/client_manager.py
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_
from app.icloud.client.caldav_client import CalDAVClient
from app.icloud.client.caldav_client_decorator import CalDAVClientDecorator
from app.icloud.models.entities import iCloudConnection
from app.utils.encryption import Encryptor
from app.utils.exceptions import CalendarError, DatabaseError, ServiceUnavailableError, wrap_external_error
from app.utils.caching import ICacheService
from app.icloud.repositories.repository import ICloudRepository
from app.icloud.services.interfaces import ICalDAVClientManager
from app.icloud.client.interfaces import ICalendarClient
from app.auth.models.entities import User
from app.utils.time_zone import TimeZone
import logging

class CalDAVClientManager(ICalDAVClientManager):
    def __init__(self, caching_service: ICacheService, repo: ICloudRepository):
        self.caching_service = caching_service
        self.repo = repo

    def get_caldav_client_for_user(self, db: Session, user_id: int) -> ICalendarClient:
        """Retrieve and configure a CalDAV client for the given user."""
        cache_key = f"icloud:client:{user_id}"
        connection_cache_key = f"icloud:connection:{user_id}"

        cached_client = self.caching_service.get(cache_key)
        if cached_client:
            cached_connection = self.caching_service.get(connection_cache_key, decrypt=True)
            try:
                current_connection = self.repo.get_icloud_connection_by_user(db, user_id)
            except Exception as e:
                raise wrap_external_error(e, DatabaseError, "Failed to retrieve iCloud connection")
            if (current_connection and cached_connection and
                    current_connection.created_at == cached_connection['created_at']):
                return cached_client

        try:
            connection = self.repo.get_icloud_connection_by_user(db, user_id)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve iCloud connection")
        if not connection:
            raise CalendarError("No iCloud connection found for user")

        self.caching_service.set(
            connection_cache_key,
            {
                'encrypted_app_password': connection.encrypted_app_password,
                'created_at': TimeZone.serialize_datetime(connection.created_at),
                'updated_at': TimeZone.serialize_datetime(connection.updated_at) if connection.updated_at else None
            },
            timeout=86400,  # 1 day
            encrypt=True
        )

        try:
            encryptor = Encryptor()
            app_password = encryptor.decrypt(connection.encrypted_app_password)
        except Exception as e:
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to decrypt iCloud password")

        try:
            user = db.query(User).filter(and_(User.id == user_id)).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve user")
        if not user:
            logging.error(f"ANOMALY: user_not_found, Details: {{'user_id': {user_id}}}")
            user_email = "unknown@example.com"
        else:
            user_email = user.email

        try:
            client = CalDAVClientDecorator(CalDAVClient(user_email=user_email, app_password=app_password))
        except Exception as e:
            raise wrap_external_error(e, CalendarError, "Failed to initialize CalDAV client")

        self.caching_service.set(cache_key, client, timeout=600)

        return client

    def connect_to_icloud(self, db: Session, user_id: int, app_password: str) -> None:
        try:
            encryptor = Encryptor()
            encrypted = encryptor.encrypt(app_password)
        except Exception as e:
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to encrypt iCloud password")
        connection = iCloudConnection(user_id=user_id, encrypted_app_password=encrypted)
        try:
            self.repo.save_icloud_connection(db, connection)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to save iCloud connection")
        self.caching_service.set(
            f"icloud:connection:{user_id}",
            {
                'encrypted_app_password': connection.encrypted_app_password,
                'created_at': TimeZone.serialize_datetime(connection.created_at),
                'updated_at': TimeZone.serialize_datetime(connection.updated_at) if connection.updated_at else None
            },
            timeout=86400,  # 1 day
            encrypt=True
        )
        self.caching_service.delete(f"icloud:client:{user_id}")
        self.caching_service.delete(f"icloud:calendars:{user_id}")

    def update_connection(self, db: Session, user_id: int, app_password: str) -> None:
        try:
            encryptor = Encryptor()
            encrypted = encryptor.encrypt(app_password)
        except Exception as e:
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to encrypt iCloud password")
        try:
            updated = self.repo.update_icloud_connection(db, user_id, encrypted)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to update iCloud connection")
        if not updated:
            raise CalendarError("No iCloud connection found to update")
        self.caching_service.set(
            f"icloud:connection:{user_id}",
            {
                'encrypted_app_password': updated.encrypted_app_password,
                'created_at': TimeZone.serialize_datetime(updated.created_at),
                'updated_at': TimeZone.serialize_datetime(updated.updated_at) if updated.updated_at else None
            },
            timeout=86400,  # 1 day
            encrypt=True
        )
        self.caching_service.delete(f"icloud:client:{user_id}")
        self.caching_service.delete(f"icloud:calendars:{user_id}")