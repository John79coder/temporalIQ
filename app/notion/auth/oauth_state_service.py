# app/notion/auth/service.py (OAuthStateService section)

from app.utils.exceptions import ServiceUnavailableError, wrap_external_error


class OAuthStateService:
    def __init__(self, caching_service):
        self.cache = caching_service

    def store_state(self, state: str, user_id: int):
        try:
            self.cache.set(
                f"oauth:state:{state}",
                {"user_id": user_id},
                timeout=300
            )
        except Exception as e:
            # Wrap and propagate — route layer will log
            raise wrap_external_error(
                e,
                ServiceUnavailableError,
                "Failed to start Notion OAuth flow"
            )

    def resolve_state(self, state: str):
        try:
            data = self.cache.get(f"oauth:state:{state}")
        except Exception as e:
            # Wrap and propagate — route layer will log
            raise wrap_external_error(
                e,
                ServiceUnavailableError,
                "Failed to verify Notion OAuth state"
            )

        if not data:
            # No logging here — route layer logs context
            return None

        return data.get("user_id")
