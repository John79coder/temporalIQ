# app/notion/auth/service.py
import requests
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.utils.exceptions import NotionError, DatabaseError, wrap_external_error
from app.utils.caching import ICacheService
from app.notion.models.entities import NotionConnection
from app.notion.models.schemas import NotionTokenIn
from config import Config
from app.notion.repositories.repository import NotionAuthRepository
from app.utils.time_zone import TimeZone
from app.utils.encryption import Encryptor
import logging

class NotionAuthService:
    def __init__(self, repo: NotionAuthRepository, caching_service: ICacheService, encryptor: Encryptor):
        self.repo = repo
        self.caching_service = caching_service
        self.token_url = "https://api.notion.com/v1/oauth/token"
        self.client_id = Config.NOTION_CLIENT_ID
        self.client_secret = Config.NOTION_CLIENT_SECRET
        self.encryptor = encryptor

    def store_access_token(self, db: Session, token_data: NotionTokenIn) -> NotionConnection:
        cache_key = f"notion:connection:{token_data.user_id}"
        with requests.Session() as session:
            try:
                response = session.post(
                    self.token_url,
                    auth=(self.client_id, self.client_secret),
                    data={
                        "grant_type": "authorization_code",
                        "code": token_data.code,
                        "redirect_uri": str(token_data.redirect_uri)
                    }
                )
                response.raise_for_status()
                response_data = response.json()
            except requests.RequestException as e:
                raise wrap_external_error(e, NotionError, "Failed to exchange Notion auth code")

        required_fields = ["access_token", "refresh_token", "expires_in", "workspace_id"]
        missing_fields = [field for field in required_fields if field not in response_data]
        if missing_fields:
            raise NotionError(f"Notion OAuth response missing required fields: {', '.join(missing_fields)}")

        expires_at = TimeZone.utc_now() + timedelta(seconds=response_data["expires_in"])
        conn = NotionConnection(
            user_id=token_data.user_id,
            access_token=self.encryptor.encrypt(response_data["access_token"]),
            refresh_token=self.encryptor.encrypt(response_data["refresh_token"]),
            expires_at=expires_at,
            workspace_id=response_data["workspace_id"]
        )

        try:
            self.repo.save_connection(db, conn)
        except SQLAlchemyError as e:
            raise wrap_external_error(e, DatabaseError, "Failed to save Notion connection")

        self.caching_service.set(
            cache_key,
            {
                'access_token': conn.access_token,
                'refresh_token': conn.refresh_token,
                'expires_at': TimeZone.serialize_datetime(conn.expires_at),
                'created_at': TimeZone.serialize_datetime(conn.created_at),
                'updated_at': TimeZone.serialize_datetime(conn.updated_at) if conn.updated_at else None,
                'workspace_id': conn.workspace_id
            },
            timeout=min(86400, response_data["expires_in"])  # NEW: Respect token expiration
        )
        return conn

    def refresh_token(self, db: Session, user_id: int) -> NotionConnection | None:
        cache_key = f"notion:connection:{user_id}"
        try:
            conn = self.repo.get_connection(db, user_id)
            if not conn or not conn.refresh_token:
                return None

            with requests.Session() as session:
                try:
                    response = session.post(
                        self.token_url,
                        auth=(self.client_id, self.client_secret),
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": self.encryptor.decrypt(conn.refresh_token)
                        }
                    )
                    response.raise_for_status()
                    response_data = response.json()
                except requests.RequestException as e:
                    raise wrap_external_error(e, NotionError, "Failed to refresh Notion token")

            required_fields = ["access_token", "refresh_token", "expires_in", "workspace_id"]
            missing_fields = [field for field in required_fields if field not in response_data]
            if missing_fields:
                raise NotionError(f"Notion OAuth refresh response missing required fields: {', '.join(missing_fields)}")

            conn.access_token = self.encryptor.encrypt(response_data["access_token"])
            conn.refresh_token = self.encryptor.encrypt(response_data["refresh_token"])
            conn.expires_at = TimeZone.utc_now() + timedelta(seconds=response_data["expires_in"])
            conn.updated_at = TimeZone.utc_now()
            conn.workspace_id = response_data["workspace_id"]

            try:
                self.repo.save_connection(db, conn)
            except SQLAlchemyError as e:
                raise wrap_external_error(e, DatabaseError, "Failed to save refreshed Notion connection")

            self.caching_service.set(
                cache_key,
                {
                    'access_token': conn.access_token,
                    'refresh_token': conn.refresh_token,
                    'expires_at': TimeZone.serialize_datetime(conn.expires_at),
                    'created_at': TimeZone.serialize_datetime(conn.created_at),
                    'updated_at': TimeZone.serialize_datetime(conn.updated_at) if conn.updated_at else None,
                    'workspace_id': conn.workspace_id
                },
                timeout=min(86400, response_data["expires_in"])  # NEW: Respect token expiration
            )
            return conn
        except requests.RequestException as e:
            raise wrap_external_error(e, NotionError, "Failed to refresh Notion token")

    def get_connection(self, db: Session, user_id: int) -> NotionConnection | None:
        cache_key = f"notion:connection:{user_id}"
        cached_connection = self.caching_service.get(cache_key)
        if cached_connection:
            required_fields = ["access_token", "refresh_token", "expires_at", "workspace_id", "user_id"]
            missing = [f for f in required_fields if f not in cached_connection]
            if missing:
                logging.warning(f"Invalid cached connection for user {user_id}: missing {missing}")
                cached_connection = None
            else:
                try:
                    return NotionConnection(**cached_connection)
                except (TypeError, KeyError) as e:
                    logging.warning(f"Corrupted cache for {cache_key}: {str(e)}")
                    cached_connection = None
        try:
            conn = self.repo.get_connection(db, user_id)
            if conn:
                self.caching_service.set(
                    cache_key,
                    conn.to_dict(),
                    timeout=86400
                )
            return conn
        except SQLAlchemyError as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve Notion connection")