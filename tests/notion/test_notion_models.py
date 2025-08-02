# tests/notion/test_models.py
import pytest
from sqlalchemy.exc import IntegrityError
from app.notion.models.entities import NotionConnection, FieldMapping, TaskCandidate
from datetime import datetime, timezone

def test_notion_connection_uniqueness(app, db_session, test_user):

    user, _ = test_user

    with app.app_context():
        conn1 = NotionConnection(
            user_id=user.id,
            access_token="token1",
            refresh_token="refresh1",
            expires_at=datetime.now(timezone.utc),
            workspace_id="Workspace1"
        )

        db_session.add(conn1)
        db_session.commit()

        conn2 = NotionConnection(
            user_id=user.id,
            access_token="token2",
            refresh_token="refresh2",
            expires_at=datetime.now(timezone.utc),
            workspace_id="Workspace1"  # same workspace ID (or whatever violates constraint)
        )
        db_session.add(conn2)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()  # Ensure session recovery



def test_field_mapping_required_fields(db_session, test_user):

    user, _ = test_user

    field_mapping = FieldMapping(user_id=user.id)

    db_session.add(field_mapping)

    with pytest.raises(IntegrityError, match="not-null constraint"):
        db_session.commit()


def test_task_candidate_creation(db_session, test_user):

    user, _ = test_user

    task_candidate = TaskCandidate(
        user_id=user.id,
        notion_db_id="db1",
        title="Test Task",
        confidence=0.9,
        issues=["Missing due date"],
        priority="high",
        status="todo",
        tags=["urgent"]
    )

    db_session.add(task_candidate)
    db_session.commit()

    retrieved_candidate = db_session.query(TaskCandidate).filter_by(user_id=user.id).first()

    assert retrieved_candidate.title == "Test Task"
    assert retrieved_candidate.confidence == 0.9
    assert retrieved_candidate.issues == ["Missing due date"]
    assert retrieved_candidate.priority == "high"
    assert retrieved_candidate.status == "todo"
    assert retrieved_candidate.tags == ["urgent"]