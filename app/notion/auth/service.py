# app/notion/auth/service.py
import logging
import time

import requests
from flask import current_app, has_request_context, request, g
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.notion.models.entities import NotionConnection
from app.notion.models.schemas import NotionTokenIn
from app.notion.repositories.repository import NotionAuthRepository
from app.utils.caching import ICacheService

from app.utils.encryption import Encryptor
from app.utils.exceptions import NotionError, DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone
from app.utils.log_event import log_event

from config import Config


def _get_correlation_id() -> str | None:
    if not has_request_context():
        return None
    return getattr(g, "correlation_id", None) or request.headers.get("X-Correlation-ID")


class NotionAuthService:
    def __init__(self, repo: NotionAuthRepository, caching_service: ICacheService, encryptor: Encryptor):
        self.repo = repo
        self.caching_service = caching_service
        self.token_url = "https://api.notion.com/v1/oauth/token"
        self.client_id = Config.NOTION_CLIENT_ID
        self.client_secret = Config.NOTION_CLIENT_SECRET
        self.encryptor = encryptor
        self.logger = current_app.logger

    def store_access_token(self, db: Session, token_data: NotionTokenIn) -> NotionConnection:
        cache_key = f"notion:connection:{token_data.user_id}"
        start = time.monotonic()

        with requests.Session() as session:
            try:
                response = session.post(
                    self.token_url,
                    auth=(self.client_id, self.client_secret),
                    data={
                        "grant_type": "authorization_code",
                        "code": token_data.code,
                        "redirect_uri": str(token_data.redirect_uri),
                    },
                )
                response.raise_for_status()
                response_data = response.json()

                log_event(
                    self.logger,
                    logging.INFO,
                    "notion_auth.oauth_exchange_success",
                    user_id=token_data.user_id,
                    status_code=response.status_code,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except requests.RequestException as e:
                log_event(
                    self.logger,
                    logging.ERROR,
                    "notion_auth.oauth_exchange_error",
                    user_id=token_data.user_id,
                    error=str(e),
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                raise wrap_external_error(e, NotionError, "Failed to exchange Notion auth code")

        required_fields = ["access_token", "refresh_token", "workspace_id"]
        missing_fields = [f for f in required_fields if f not in response_data]
        if missing_fields:
            log_event(
                self.logger,
                logging.ERROR,
                "notion_auth.oauth_missing_fields",
                user_id=token_data.user_id,
                missing_fields=missing_fields,
            )
            raise NotionError(f"Notion OAuth response missing required fields: {', '.join(missing_fields)}")

        conn = NotionConnection(
            user_id=token_data.user_id,
            access_token=self.encryptor.encrypt(response_data["access_token"]),
            refresh_token=self.encryptor.encrypt(response_data["refresh_token"]),
            expires_at=None,
            workspace_id=response_data["workspace_id"],
        )

        try:
            db_start = time.monotonic()

            self.repo.save_connection(db, conn)

            db.commit()

            log_event(
                self.logger,
                logging.INFO,
                "notion_auth.connection_saved",
                user_id=token_data.user_id,
                duration_ms=int((time.monotonic() - db_start) * 1000),
            )

        except SQLAlchemyError as e:
            log_event(
                self.logger,
                logging.ERROR,
                "notion_auth.connection_save_error",
                user_id=token_data.user_id,
                error=str(e),
            )
            raise wrap_external_error(e, DatabaseError, "Failed to save Notion connection")

        cache_start = time.monotonic()

        self.caching_service.set(
            cache_key,
            {
                "user_id": conn.user_id,
                "access_token": conn.access_token,
                "refresh_token": conn.refresh_token,
                "expires_at": (
                    TimeZone.serialize_datetime(conn.expires_at)
                    if conn.expires_at else None
                    ),
                "created_at": TimeZone.serialize_datetime(conn.created_at),
                "updated_at": TimeZone.serialize_datetime(conn.updated_at) if conn.updated_at else None,
                "workspace_id": conn.workspace_id,
            },
            timeout=86400,
        )

        response.raise_for_status()

        log_event(
            self.logger,
            logging.INFO,
            "notion_auth.oauth_exchange_success",
            user_id=token_data.user_id,
            status_code=response.status_code,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

        return conn

    def refresh_token(self, db: Session, user_id: int) -> NotionConnection | None:
        cache_key = f"notion:connection:{user_id}"

        try:
            conn = self.repo.get_connection(db, user_id)
            if not conn or not conn.refresh_token:
                log_event(
                    self.logger,
                    logging.INFO,
                    "notion_auth.no_refresh_token",
                    user_id=user_id,
                )
                return None

            start = time.monotonic()
            with requests.Session() as session:
                try:
                    response = session.post(
                        self.token_url,
                        auth=(self.client_id, self.client_secret),
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": self.encryptor.decrypt(conn.refresh_token),
                        },
                    )
                    response.raise_for_status()
                    response_data = response.json()
                    log_event(
                        self.logger,
                        logging.INFO,
                        "notion_auth.refresh_success",
                        user_id=user_id,
                        status_code=response.status_code,
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                except requests.RequestException as e:
                    log_event(
                        self.logger,
                        logging.ERROR,
                        "notion_auth.refresh_http_error",
                        user_id=user_id,
                        error=str(e),
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                    raise wrap_external_error(e, NotionError, "Failed to refresh Notion token")

            required_fields = ["access_token", "refresh_token", "workspace_id"]
            missing_fields = [f for f in required_fields if f not in response_data]
            if missing_fields:
                log_event(
                    self.logger,
                    logging.ERROR,
                    "notion_auth.refresh_missing_fields",
                    user_id=user_id,
                    missing_fields=missing_fields,
                )
                raise NotionError(
                    f"Notion OAuth refresh response missing required fields: {', '.join(missing_fields)}"
                )

            conn.access_token = self.encryptor.encrypt(response_data["access_token"])
            conn.refresh_token = self.encryptor.encrypt(response_data["refresh_token"])
            conn.updated_at = TimeZone.utc_now()
            conn.workspace_id = response_data["workspace_id"]

            try:
                db_start = time.monotonic()
                self.repo.save_connection(db, conn)
                log_event(
                    self.logger,
                    logging.INFO,
                    "notion_auth.refresh_connection_saved",
                    user_id=user_id,
                    duration_ms=int((time.monotonic() - db_start) * 1000),
                )

            except Exception as e:
                self.logger.exception("save_connection/commit failed")
                raise

            cache_start = time.monotonic()
            self.caching_service.set(
                cache_key,
                {
                    "user_id": conn.user_id,
                    "access_token": conn.access_token,
                    "refresh_token": conn.refresh_token,
                    "expires_at": (
                        TimeZone.serialize_datetime(conn.expires_at)
                        if conn.expires_at else None
                                ),
                    "created_at": TimeZone.serialize_datetime(conn.created_at),
                    "updated_at": TimeZone.serialize_datetime(conn.updated_at) if conn.updated_at else None,
                    "workspace_id": conn.workspace_id,
                },
                timeout=86400,
            )
            log_event(
                self.logger,
                logging.INFO,
                "notion_auth.refresh_connection_cached",
                user_id=user_id,
                cache_key=cache_key,
                duration_ms=int((time.monotonic() - cache_start) * 1000),
            )
            return conn

        except requests.RequestException as e:
            log_event(
                self.logger,
                logging.ERROR,
                "notion_auth.refresh_unexpected_request_error",
                user_id=user_id,
                error=str(e),
            )
            raise wrap_external_error(e, NotionError, "Failed to refresh Notion token")

    def get_connection(self, db: Session, user_id: int) -> NotionConnection | None:
        cache_key = f"notion:connection:{user_id}"
        cached = self.caching_service.get(cache_key)

        if cached:
            required = ["access_token", "refresh_token", "workspace_id", "user_id"]
            missing = [f for f in required if f not in cached]

            if missing:
                log_event(
                    self.logger,
                    logging.WARNING,
                    "notion_auth.invalid_cache",
                    user_id=user_id,
                    cache_key=cache_key,
                    missing_fields=missing,
                )
                cached = None
            else:
                try:
                    log_event(
                        self.logger,
                        logging.INFO,
                        "notion_auth.cache_hit",
                        user_id=user_id,
                        cache_key=cache_key,
                    )
                    return NotionConnection(**cached)
                except (TypeError, KeyError) as e:
                    log_event(
                        self.logger,
                        logging.WARNING,
                        "notion_auth.cache_corrupted",
                        user_id=user_id,
                        cache_key=cache_key,
                        error=str(e),
                    )
                    cached = None

        try:
            start = time.monotonic()
            conn = self.repo.get_connection(db, user_id)
            duration_ms = int((time.monotonic() - start) * 1000)

            if conn:
                cache_start = time.monotonic()
                self.caching_service.set(cache_key, conn.to_dict(), timeout=86400)
                log_event(
                    self.logger,
                    logging.INFO,
                    "notion_auth.db_connection_loaded",
                    user_id=user_id,
                    cache_key=cache_key,
                    db_duration_ms=duration_ms,
                    cache_duration_ms=int((time.monotonic() - cache_start) * 1000),
                )
            else:
                log_event(
                    self.logger,
                    logging.INFO,
                    "notion_auth.db_connection_missing",
                    user_id=user_id,
                    db_duration_ms=duration_ms,
                )

            return conn
        except SQLAlchemyError as e:
            log_event(
                self.logger,
                logging.ERROR,
                "notion_auth.db_connection_error",
                user_id=user_id,
                error=str(e),
            )
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve Notion connection")
