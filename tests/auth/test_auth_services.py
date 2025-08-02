# tests/auth/test_services.py
from datetime import datetime, timezone
import pytest
from unittest.mock import patch
from app.auth.email_verification.service import EmailVerificationService
from app.auth.email_verification.repository import TokenRepository
from app.utils.exceptions import DataValidationError, AuthError
from tests.conftest import DEFAULT_TEST_PASSWORD


@patch("app.auth.email_verification.service.mail.send")
def test_email_verification_service_create_token(mock_send, db_session, app, caching_service, test_user):

    user, _ = test_user

    with app.app_context():

        service = EmailVerificationService(TokenRepository(), caching_service)

        verification_token = service.create_email_verification_token(db_session, user.id, user.email)

        assert verification_token.user_id == user.id
        assert verification_token.token is not None
        assert verification_token.expires_at > datetime.now(timezone.utc)

        mock_send.assert_called_once()


@patch("app.auth.email_verification.service.mail.send")
def test_email_verification_service_invalid_email(mock_send, db_session, app, caching_service, test_user):

    user, _ = test_user

    with app.app_context():

        service = EmailVerificationService(TokenRepository(), caching_service)

        with pytest.raises(DataValidationError, match="email address"):

            service.create_email_verification_token(db_session, user.id, "invalid-email")


def test_authentication_service_authenticate_user(db_session, test_user, authentication_service):

    user, _ = test_user

    authenticated_user = authentication_service.authenticate_user(db_session, user.email, DEFAULT_TEST_PASSWORD)

    assert authenticated_user.email == user.email
    assert authenticated_user.id == user.id

@patch("app.auth.session_manager.service.pwd_context.verify")
def test_authentication_service_password_hash_failure(mock_verify, db_session, app, authentication_service, test_user):

    user, _ = test_user

    with app.app_context():

        mock_verify.side_effect = Exception("Hash error")

        with pytest.raises(AuthError, match="Hash error"):
            authentication_service.authenticate_user(db_session, user.email, DEFAULT_TEST_PASSWORD)