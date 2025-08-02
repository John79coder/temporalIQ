# tests/user/test_models.py
import pytest
from sqlalchemy.exc import IntegrityError
from app.user_preferences.models.entities import UserPreferences


def test_user_preferences__defaults(db_session, test_user):

    user, _ = test_user

    user_preferences = UserPreferences(user_id=user.id)
    db_session.add(user_preferences)
    db_session.commit()

    assert user_preferences.block_size_minutes == 30
    assert user_preferences.max_blocks_per_day == 16
    assert user_preferences.work_hours == 7.6
    assert user_preferences.allow_weekends is False


def test_user_preferences_invalid_work_hours(db_session, test_user):

    user, _ = test_user

    user_preferences = UserPreferences(
        user_id=user.id,
        work_hours=-1
    )
    db_session.add(user_preferences)

    with pytest.raises(IntegrityError, match="check_work_hours_positive"):
        db_session.commit()