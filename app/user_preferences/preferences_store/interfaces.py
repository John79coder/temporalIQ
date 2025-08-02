# app/user_preferences/preferences_store/interfaces.py

from abc import ABC, abstractmethod
from typing import Optional
from sqlalchemy.orm import Session
from app.user_preferences.models.entities import UserPreferences
from app.user_preferences.models.schemas import PreferencesCreate


class IPreferencesService(ABC):
    @abstractmethod
    def save_preferences(self, db: Session, prefs: PreferencesCreate) -> UserPreferences:
        pass

    @abstractmethod
    def get_preferences(self, db: Session, user_id: int) -> Optional[UserPreferences]:
        pass
