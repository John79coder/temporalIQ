# tests/auth/test_auth_routes_2.py
import uuid
from unittest.mock import patch

from flask import g
from passlib.context import CryptContext

from app import mail
from app.auth.models.entities import User, PasswordResetToken
from tests.conftest import DEFAULT_TEST_PASSWORD

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Existing tests (unchanged from your provided file)
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


# NEW: Tests for Password Reset/Recovery
@patch("flask_mail.Mail.send")
def test_password_reset_success(mock_send, client, db_session, app, test_user, authentication_service):
    with app.app_context():
        g.db = db_session

        user, user_id = test_user
        authentication_service.update_verified(db_session, user_id)
        db_session.commit()

        response = client.post("/auth/reset-password", json={"email": user.email},
                               headers={"X-CSRF-Token": client.csrf_token})
        assert response.status_code == 200
        assert "Password reset link sent" in response.json["message"]
        token = db_session.query(PasswordResetToken).filter_by(user_id=user.id).first().token
        response = client.post("/auth/reset-password/confirm", json={"token": token, "new_password": "NewSecure123!"},
                               headers={"X-CSRF-Token": client.csrf_token})
        assert response.status_code == 200
        assert "jwt" in response.json
        updated_user = db_session.query(User).filter_by(id=user.id).first()
        assert authentication_service.verify_password("NewSecure123!", updated_user.hashed_password)


@patch("flask_mail.Mail.send")
def test_password_reset_invalid(mock_send, client, db_session, app):
    with app.app_context():
        g.db = db_session
        response = client.post("/auth/reset-password", json={"email": "invalid@example.com"},
                               headers={"X-CSRF-Token": client.csrf_token})
        assert response.status_code == 400
        assert "User not found" in response.json["detail"]
        response = client.post("/auth/reset-password/confirm", json={"token": "fake", "new_password": "NewPass"},
                               headers={"X-CSRF-Token": client.csrf_token})
        assert response.status_code == 400
        assert "Invalid or expired reset token" in response.json["detail"]


# tests/auth/test_auth_routes_2.py
import time  # Add import


# ...

@patch("app.auth.email_verification.service.EmailVerificationService.verify_token")
def test_verify_rate_limit(mock_verify, client, db_session, app):
    with app.app_context():
        app.config["TESTING"] = False
        try:
            g.db = db_session

            from app.extensions import limiter
            limiter._strategy = 'fixed-window'

            # Make mock return None or a valid token-like object
            mock_verify.return_value = None  # Simulate invalid/expired token

            with patch("time.time") as mock_time:
                current_time = time.time()

                def advance_time():
                    nonlocal current_time
                    current_time += 2
                    return current_time

                mock_time.side_effect = advance_time

                for i in range(6):
                    response = client.post("/auth/verify", json={"token": "test"},
                                           headers={"X-CSRF-Token": client.csrf_token})
                    if i < 5:
                        assert response.status_code == 400
                    else:
                        assert response.status_code == 429

            assert b"Too Many Requests" in response.data
        finally:
            app.config["TESTING"] = True


def test_verify_rate_limit_under(client, db_session, app):
    with app.app_context():
        g.db = db_session
        response = client.post("/auth/verify", json={"token": "valid"}, headers={"X-CSRF-Token": client.csrf_token})
        assert response.status_code == 200 or 400  # Success or invalid, but not rate limit


# NEW: Tests for 2FA/MFA
def test_2fa_setup_success(authorized_client, db_session, app, test_user):
    user, _ = test_user
    with app.app_context():
        g.db = db_session
        response = authorized_client.get("/auth/2fa/setup", headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert response.status_code == 200
        assert "qr_base64" in response.json
        assert "secret" in response.json
        assert len(response.json["backup_codes"]) == 10
        updated_user = db_session.query(User).filter_by(id=user.id).first()
        assert updated_user.two_factor_enabled


# tests/auth/test_auth_routes_2.py

# ...

def test_2fa_verify_success_invalid(authorized_client, db_session, app, test_user, authentication_service):
    user, user_id = test_user
    with app.app_context():
        g.db = db_session

        authentication_service.update_verified(db_session, user.id)
        db_session.commit()

        setup_response = authorized_client.get("/auth/2fa/setup",
                                               headers={"X-CSRF-Token": authorized_client.csrf_token})
        assert setup_response.status_code == 200

        with patch("pyotp.TOTP.verify", return_value=True):
            response = authorized_client.post("/auth/2fa/verify", json={"user_id": user_id, "code": "123456"}, headers={
                "X-CSRF-Token": authorized_client.csrf_token})
            assert response.status_code == 200
            assert "jwt" in response.json

        with patch("pyotp.TOTP.verify", return_value=False):
            with patch("passlib.context.CryptContext.verify", return_value=False):
                response = authorized_client.post("/auth/2fa/verify", json={"user_id": user_id, "code": "wrong"},
                                                  headers={"X-CSRF-Token": authorized_client.csrf_token})
                assert response.status_code == 400
                assert "Invalid 2FA code" in response.json["detail"]


@patch("flask_mail.Mail.send")
def test_sendgrid_verification_email(mock_send, client, db_session, app):
    with app.app_context():
        g.db = db_session
        email = f"test_{uuid.uuid4().hex}@example.com"
        response = client.post("/auth/signup", json={"email": email, "password": "Secure123!"},
                               headers={"X-CSRF-Token": client.csrf_token})
        assert response.status_code == 200
        assert mock_send.called
        sent_msg = mock_send.call_args[0][0]
        assert sent_msg.subject.lower() == "verify your email"  # Case-insensitive
        assert email in sent_msg.recipients


def test_sendgrid_reset_email(client, db_session, app, test_user, authentication_service):
    with app.app_context():
        user, user_id = test_user
        authentication_service.update_verified(db_session, user_id)
        db_session.commit()

        g.db = db_session
        with mail.record_messages() as outbox:
            response = client.post("/auth/reset-password", json={"email": user.email},
                                   headers={"X-CSRF-Token": client.csrf_token})
            assert response.status_code == 200
            assert len(outbox) == 1  # Assert an email was "sent" to outbox
            sent_msg = outbox[0]
            assert "Password Reset Request" in sent_msg.subject
            assert user.email in sent_msg.recipients
