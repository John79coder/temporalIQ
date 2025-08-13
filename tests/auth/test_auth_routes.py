# tests/auth/test_routes.py
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock

import jwt
from flask import g
from passlib.context import CryptContext

from app.auth.models.entities import User, VerificationToken
from tests.conftest import DEFAULT_TEST_PASSWORD

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@patch("app.auth.email_verification.service.mail.send")
def test_signup_success(mock_send, client, db_session, app):
    with app.app_context():
        g.db = db_session

        email = f"test_signup_{uuid.uuid4().hex}@example.com"

        response = client.post("/auth/signup", json={
            "email": email,
            "password": "Secure123!"
        }, headers={"X-CSRF-Token": client.csrf_token})

        assert response.status_code == 200
        assert "user" in response.json
        assert response.json["user"]["email"] == email
        assert "jwt" in response.json
        assert "token" in response.json

        user = db_session.query(User).filter_by(email=email).first()

        assert user is not None
        assert not user.is_verified


def test_signup_duplicate_email(client, db_session, app, test_user):
    user, _ = test_user

    response = client.post("/auth/signup", json={
        "email": user.email,
        "password": DEFAULT_TEST_PASSWORD
    }, headers={"X-CSRF-Token": client.csrf_token})

    assert response.status_code == 401
    assert "Email already exists" in response.json["detail"]


def test_signup_invalid_input(authorized_client, db_session, app):
    with app.app_context():
        g.db = db_session

        response = authorized_client.post("/auth/signup", json={
            "email": "invalid",
            "password": "weak"
        }, headers={"X-CSRF-Token": authorized_client.csrf_token})

        print("=== RESPONSE ===")
        print("Status code:", response.status_code)
        print("Response data:", response.data.decode())

        assert response.status_code == 400
        assert "email address" in response.json["detail"]
    assert "Password must be at least 8 characters" in response.json["detail"]


def test_signup_missing_csrf(client, db_session, app):
    app.config["WTF_CSRF_ENABLED"] = False

    try:
        with app.app_context():

            _ = client.csrf_token

            response = client.post("/auth/signup", json={
                "email": "test@example.com",
                "password": "Secure123!"
            }, headers={"X-CSRF-Token": "abc.def.ghi"})

            assert response.status_code == 403
            assert "Invalid CSRF token" in response.json["detail"]
    finally:
        app.config["WTF_CSRF_ENABLED"] = True


@patch("app.auth.email_verification.service.mail.send")
def test_signup_database_failure(mock_send, client, db_session, app):
    with patch("app.auth.session_manager.repository.UserRepository.create", side_effect=Exception("DB error")):
        response = client.post("/auth/signup", json={
            "email": f"test_db_fail_{uuid.uuid4().hex}@example.com",
            "password": DEFAULT_TEST_PASSWORD
        }, headers={"X-CSRF-Token": client.csrf_token})

        assert response.status_code == 500
        assert "DB error" in response.json["detail"]


def test_login_success(client, db_session, app, test_user, authentication_service):
    user, _ = test_user

    authentication_service.update_verified(db_session, user.id)

    response = client.post("/auth/login", json={
        "email": user.email,
        "password": DEFAULT_TEST_PASSWORD
    }, headers={"X-CSRF-Token": client.csrf_token})

    assert response.status_code == 200
    assert "user" in response.json

    assert response.json["user"]["email"] == user.email

    assert "jwt" in response.json

    decoded = jwt.decode(response.json["jwt"], app.config["JWT_SECRET_KEY"], algorithms=["HS256"])

    assert int(decoded["sub"]) == user.id


def test_login_invalid_credentials(client, db_session, app, test_user):
    user, _ = test_user

    response = client.post("/auth/login", json={
        "email": user.email,
        "password": "WrongP123!"
    }, headers={"X-CSRF-Token": client.csrf_token})

    assert response.status_code == 401
    assert "Invalid email or password" in response.json["detail"]


def test_login_unverified_user(client, db_session, app):
    email = f"{uuid.uuid4().hex}@example.com"

    user = User(email=email, hashed_password=pwd_context.hash(DEFAULT_TEST_PASSWORD), is_verified=False)

    db_session.add(user)
    db_session.commit()

    response = client.post("/auth/login", json={
        "email": user.email,
        "password": DEFAULT_TEST_PASSWORD
    }, headers={"X-CSRF-Token": client.csrf_token})

    assert response.status_code == 403
    assert "Account not verified" in response.json["detail"]


def test_login_missing_fields(client, db_session, app):
    with app.app_context():
        g.db = db_session

        response = client.post("/auth/login", json={
            "email": "",
            "password": ""
        }, headers={"X-CSRF-Token": client.csrf_token})

        assert response.status_code == 400
        assert "email address" in response.json["detail"]
        assert "password" in response.json["detail"]


def test_login_database_failure(client, db_session, app):
    with app.app_context():
        g.db = db_session

        email = f"test_db_fail_{uuid.uuid4().hex}@example.com"

        with patch("app.auth.session_manager.repository.UserRepository.get_by_email",
                   side_effect=Exception("DB error")):
            response = client.post("/auth/login", json={
                "email": email,
                "password": "Secure123!"
            }, headers={"X-CSRF-Token": client.csrf_token})

            assert response.status_code == 500
            assert "DB error" in response.json["detail"]


def test_verify_email_success(client, db_session, app, test_user):
    user, _ = test_user

    with app.app_context():
        g.db = db_session

        token = "test-token"

        verification_token = VerificationToken(user_id=user.id, token=token,
                                               expires_at=datetime.now(timezone.utc) + timedelta(minutes=15))

        db_session.add(verification_token)
        db_session.commit()

        response = client.post("/auth/verify", json={"token": token}, headers={"X-CSRF-Token": client.csrf_token})

        assert response.status_code == 200
        assert response.json["user"]["is_verified"] is True
        assert "jwt" in response.json


def test_verify_invalid_token(client, db_session, app):
    with app.app_context():
        response = client.post("/auth/verify", json={"token": "invalid"}, headers={"X-CSRF-Token": client.csrf_token})

        assert response.status_code == 400
        assert "Invalid or expired token" in response.json["detail"]


def test_verify_missing_csrf(client, db_session, app):
    app.config["WTF_CSRF_ENABLED"] = False

    try:
        with app.app_context():

            g.db = db_session
            _ = client.csrf_token

            response = client.post("/auth/verify", json={
                "email": "test@example.com",
                "password": "Secure123!"
            }, headers={"X-CSRF-Token": "abc.def.ghi"})

            assert response.status_code == 403
            assert "Invalid CSRF token" in response.json["detail"]

    finally:
        app.config["WTF_CSRF_ENABLED"] = True


@patch("requests.Session.get")
def test_apple_signin_success(mock_get, client, db_session, app, test_user):
    user, _ = test_user

    with app.app_context():
        g.db = db_session
        mock_get.return_value = Mock(
            json=Mock(return_value={"keys": [{"kid": "test-kid", "kty": "RSA"}]}))  # Mock response

        with patch("app.auth.session_manager.service.AuthenticationService.authenticate_apple_user", return_value=user):
            response = client.post("/auth/apple-signin", json={"id_token": "fake-token"},
                                   headers={"X-CSRF-Token": client.csrf_token})

            assert response.status_code == 200
            assert response.json["user"]["email"] == user.email
            assert "jwt" in response.json


def test_apple_signin_missing_id_token(client, db_session, app):
    with app.app_context():
        g.db = db_session
        response = client.post("/auth/apple-signin", json={}, headers={"X-CSRF-Token": client.csrf_token})

        assert response.status_code == 400
        assert "Missing id_token" in response.json["detail"]


def test_onboarding_success(authorized_client, app):
    response = authorized_client.get("/auth/onboarding")

    assert response.status_code == 200
    assert "steps" in response.json
    assert len(response.json["steps"]) == 5
    assert response.json["steps"][0]["title"] == "Sign Up"


def test_test_session_success(client, app):
    response = client.post("/auth/test-session", json={})

    assert response.status_code == 200
    assert "csrf_token" in response.json
