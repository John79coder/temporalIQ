import logging

from app.utils.exceptions import ServiceUnavailableError, wrap_external_error

logger = logging.getLogger(__name__)


class OAuthStateService:
    def __init__(self, caching_service):
        self.cache = caching_service

    def store_state(self, state: str, user_id: int):
        try:
            self.cache.set(f"oauth:state:{state}", {"user_id": user_id}, timeout=300)
        except Exception as e:
            logger.error("Failed to store OAuth state for user %s: %s", user_id, e)
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to start Notion OAuth flow")

    def resolve_state(self, state: str):
        try:
            data = self.cache.get(f"oauth:state:{state}")
        except Exception as e:
            logger.error("Failed to resolve OAuth state: %s", e)
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to verify Notion OAuth state")
        if not data:
            logger.warning("OAuth state not found or expired: %s", state)
            return None
        return data.get("user_id")