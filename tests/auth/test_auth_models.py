# tests/auth/test_models.py
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.models.entities import User
from app.auth.models.entities import VerificationToken
from app.utils.exceptions import AuthError
from tests.conftest import PASSWORD_CONTEXT

"""
    This test verifies that a User object can be created and persisted correctly.
    LAYER: ORM model + DB integration.
"""
def test_user_model_creation(db_session):
    user = User(
        email="test@example.com",
        hashed_password=PASSWORD_CONTEXT.hash("Secure123!"),
        is_verified=False
    )

    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.hashed_password is not None
    assert user.created_at is not None
    assert user.is_verified is False


"""
    This test ensures that a VerificationToken with an expired timestamp is stored correctly and can be retrieved.
    LAYER: ORM model + datetime handling.
"""
def test_verification_token_expiration(db_session, test_user):
    user, _ = test_user

    verification_token = VerificationToken(
        user_id=user.id,
        token="test-token",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    db_session.add(verification_token)
    db_session.commit()

    retrieved = db_session.query(VerificationToken).filter_by(token="test-token").first()

    assert retrieved.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)

"""
    Verify that invalid emails are rejected at the database level, not just at the service or schema level.
    LAYER: Database constraints (CHECK constraints)    
"""
def test_user_model_invalid_email(db_session):
    user = User(
        email="invalid-email",
        hashed_password=PASSWORD_CONTEXT.hash("Secure123!")
    )

    db_session.add(user)

    with pytest.raises(IntegrityError, match="valid_email"):
        db_session.commit()

"""
    Ensure tokens cannot exist without a user.
    LAYER: Data.
"""
def test_verification_token_missing_user(db_session):
    verification_token = VerificationToken(
        token="test-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )

    db_session.add(verification_token)

    with pytest.raises(IntegrityError, match="not-null constraint"):
        db_session.commit()

"""
    Ensure your service layer wraps low‑level DB errors into clean, user‑facing exceptions.
    LAYER: Service.
"""
def test_db_constraint_violation_handling(db_session, authentication_service):
    authentication_service.create_user(db_session, "dup@example.com", "pass")
    with pytest.raises(AuthError, match="Email already exists"):
        authentication_service.create_user(db_session, "dup@example.com", "pass")
