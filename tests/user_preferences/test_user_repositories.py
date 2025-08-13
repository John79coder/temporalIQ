# tests/user/test_repositories.py
import pytest

from app.user_preferences.models.entities import UserPreferences
from app.user_preferences.preferences_store.repository import PreferencesRepository
from app.utils.exceptions import DatabaseError


def test_preferences_repository__create_or_update(db_session, test_user):
    user, _ = test_user

    user_preferences_repository = PreferencesRepository()

    user_preferences = UserPreferences(
        user_id=user.id,
        block_size_minutes=60,
        max_blocks_per_day=8,
        work_hours=8.0,
        allow_weekends=True
    )

    user_preferences_repository.create_or_update(db_session, user_preferences)
    retrieved_preferences = db_session.query(UserPreferences).filter_by(user_id=user.id).first()

    assert retrieved_preferences.block_size_minutes == 60
    assert retrieved_preferences.max_blocks_per_day == 8
    assert retrieved_preferences.work_hours == 8.0
    assert retrieved_preferences.allow_weekends is True


def test_preferences_repository_invalid_update(db_session, test_user):
    user, _ = test_user

    user_preferences_repository = PreferencesRepository()

    user_preferences = UserPreferences(
        user_id=user.id,
        block_size_minutes=0,
        max_blocks_per_day=0,
        work_hours=-1
    )

    with pytest.raises(DatabaseError, match="Block size must be positive"):
        user_preferences_repository.create_or_update(db_session, user_preferences)
