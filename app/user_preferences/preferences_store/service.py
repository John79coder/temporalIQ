# app/user_preferences/preferences_store/service.py
import logging

from app.user_preferences.models.entities import UserPreferences
from app.user_preferences.models.schemas import PreferencesCreate
from app.user_preferences.preferences_store.interfaces import IPreferencesService
from app.user_preferences.preferences_store.repository import PreferencesRepository
from app.utils.caching import ICacheService
from app.utils.exceptions import DatabaseError, wrap_external_error


class PreferencesService(IPreferencesService):
    def __init__(self, repo: PreferencesRepository, caching_service: ICacheService):
        self.repo = repo
        self.caching_service = caching_service

    def save_preferences(self, db, prefs: PreferencesCreate):
        entity = UserPreferences(**prefs.model_dump())
        try:
            saved = self.repo.create_or_update(db, entity)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to save preferences")
        cache_key = f"user:{prefs.user_id}:preferences"
        self.caching_service.delete(cache_key)  # Explicit delete before set (Issue 7)
        self.caching_service.set(
            cache_key,
            saved.__dict__,
            timeout=86400  # 1 day
        )
        return saved

    def get_preferences(self, db, user_id: int):
        cache_key = f"user:{user_id}:preferences"
        cached_prefs = self.caching_service.get(cache_key)
        if cached_prefs:
            return UserPreferences.from_dict(cached_prefs)
        try:
            prefs = self.repo.get_by_user(db, user_id)
            if not prefs:
                # Create and save defaults if none found (Issue 6)
                logging.warning(f"No preferences found for user {user_id}, creating defaults")
                default_prefs = PreferencesCreate(user_id=user_id)
                prefs = self.save_preferences(db, default_prefs)
            self.caching_service.set(
                cache_key,
                prefs.__dict__,
                timeout=86400  # 1 day
            )
            return prefs
        except Exception as e:
            logging.error(f"Failed to get preferences for user {user_id}: {str(e)}")
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve preferences")

    def reset_preferences(self, db, user_id: int):  # Added for Issue 8
        try:
            self.repo.delete_by_user(db, user_id)
            default_prefs = PreferencesCreate(user_id=user_id)
            return self.save_preferences(db, default_prefs)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to reset preferences")
