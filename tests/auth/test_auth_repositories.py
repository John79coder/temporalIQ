# tests/auth/test_repositories.py
from datetime import datetime, timezone, timedelta

from app.auth.email_verification.repository import TokenRepository
from app.auth.models.entities import VerificationToken
from app.auth.session_manager.repository import UserRepository


def test_token_repository_create(db_session, test_user):
    user, _ = test_user

    token_repository = TokenRepository()

    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    verification_token = token_repository.create(db_session, user_id=user.id, token="test-token", expires_at=expires)

    assert verification_token.user_id == user.id
    assert verification_token.token == "test-token"
    assert verification_token.expires_at == expires

    retrieved = db_session.query(VerificationToken).filter_by(token="test-token").first()

    assert retrieved is not None


def test_user_repository_get_by_email(db_session, test_user):
    user, _ = test_user

    repo = UserRepository()

    retrieved = repo.get_by_email(db_session, user.email)

    assert retrieved.email == user.email
    assert retrieved.id == user.id


def test_user_repository_nonexistent_email(db_session):
    repo = UserRepository()

    result = repo.get_by_email(db_session, "nonexistent@example.com")

    assert result is None
