# tests/user/test_services.py
from app.auth.models.entities import User
from app.user_preferences.models.entities import UserPreferences
from app.user_preferences.models.schemas import PreferencesCreate
from app.user_preferences.preferences_store.repository import PreferencesRepository
from app.user_preferences.preferences_store.service import PreferencesService


def test_preferences_service_save_preferences(caching_service, db_session, app):
    with app.app_context():
        user = User(email="test@example.com", hashed_password="hashed")
        db_session.add(user)
        db_session.commit()
        service = PreferencesService(PreferencesRepository(), caching_service)
        prefs = PreferencesCreate(
            user_id=user.id,
            block_size_minutes=60,
            max_blocks_per_day=8,
            work_hours=8.0,
            allow_weekends=True
        )
        service.save_preferences(db_session, prefs)
        retrieved = db_session.query(UserPreferences).filter_by(user_id=user.id).first()
        assert retrieved.block_size_minutes == 60
        assert retrieved.work_hours == 8.0
