# tests/user/test_routes.py
from unittest.mock import patch
from flask import g
from app.user_preferences.models.entities import UserPreferences
from app.auth.models.entities import User
from app.utils.time_zone import TimeZone


def test_set_preferences__success(authorized_client, db_session, app, test_user):

    _, user_id = test_user

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)

        response = authorized_client.post("/user/preferences", json={
            "user_id": user_id,
            "block_size_minutes": 30,
            "allow_weekends": False,
            "max_blocks_per_day": 16,
            "work_hours": 7.6
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200
        assert response.json["block_size_minutes"] == 30
        assert response.json["work_hours"] == 7.6

        retrieved_preferences = db_session.query(UserPreferences).filter_by(user_id=user_id).first()

        assert retrieved_preferences is not None
        assert retrieved_preferences.block_size_minutes == 30


def test_set_preferences__invalid_input(authorized_client, db_session, app, test_user):

    _, user_id = test_user

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)

        response = authorized_client.post("/user/preferences", json={
            "user_id": user_id,
            "block_size_minutes": 0,
            "allow_weekends": True,
            "max_blocks_per_day": 0,
            "work_hours": 100
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 400
        assert "Block size must be greater than zero" in response.json["detail"]


def test_set_preferences__unauthorized(authorized_client, db_session, app, test_user):

    _, user_id = test_user

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)

        response = authorized_client.post("/user/preferences", json={
            "user_id": user_id + 1,
            "block_size_minutes": 30,
            "allow_weekends": False,
            "max_blocks_per_day": 16,
            "work_hours": 7.6
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 403
        assert "Unauthorized access" in response.json["detail"]


@patch("app.user_preferences.preferences_store.repository.PreferencesRepository.create_or_update")
def test_set_preferences__database_failure(mock_create, authorized_client, db_session, app, test_user):

    _, user_id = test_user
    mock_create.side_effect = Exception("DB error")

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)

        response = authorized_client.post("/user/preferences", json={
            "user_id": user_id,
            "block_size_minutes": 30,
            "allow_weekends": False,
            "max_blocks_per_day": 16,
            "work_hours": 7.6
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 500
        assert "DB error" in response.json["detail"]


def test_get_preferences__success(authorized_client, db_session, app, test_user):

    _, user_id = test_user

    with app.app_context():

        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)

        user_preferences = UserPreferences(user_id=user_id, block_size_minutes=30, allow_weekends=False, max_blocks_per_day=16, work_hours=7.6)

        db_session.add(user_preferences)
        db_session.commit()

        response = authorized_client.get(f"/user/preferences/{user_id}", headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200
        assert response.json["block_size_minutes"] == 30
        assert response.json["work_hours"] == 7.6


def test_get_preferences(authorized_client, db_session, app, test_user):
    user, user_id = test_user
    with app.app_context():
        response = authorized_client.get(f"/user/preferences/{user_id}", headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 200

        user_preferences = UserPreferences.from_dict( response.json)

        assert user_preferences.user_id == user_id



def test_get_preferences__unauthorized(authorized_client, db_session, app, test_user):

    _, user_id = test_user

    with app.app_context():
        g.db = db_session
        g.current_user = db_session.query(User).get(user_id)

        response = authorized_client.get(f"/user/preferences/{user_id + 1}", headers={"X-CSRF-Token": authorized_client.csrf_token})

        assert response.status_code == 403
        assert "Unauthorized access" in response.json["detail"]