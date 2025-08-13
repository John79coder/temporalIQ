# tests/notion/test_repositories.py
from datetime import datetime, timezone

from app.notion.mapping_storage.repository import MappingRepository
from app.notion.models.entities import NotionConnection, FieldMapping, TaskCandidate
from app.notion.repositories.repository import TaskCandidateRepository, NotionAuthRepository


def test_notion_auth_repository_save_connection(db_session, test_user):
    user, _ = test_user

    notion_auth_repository = NotionAuthRepository()

    notion_connection = NotionConnection(
        user_id=user.id,
        access_token="test-token",
        refresh_token="test-refresh",
        expires_at=datetime.now(timezone.utc),
        workspace_id="Test Workspace"
    )

    notion_auth_repository.save_connection(db_session, notion_connection)

    retrieved_connection = db_session.query(NotionConnection).filter_by(user_id=user.id).first()

    assert retrieved_connection.access_token == "test-token"
    assert retrieved_connection.refresh_token == "test-refresh"
    assert retrieved_connection.workspace_id == "Test Workspace"


def test_mapping_repository_save(db_session, test_user):
    user, _ = test_user

    mapping_repository = MappingRepository()

    field_mapping = FieldMapping(
        user_id=user.id,
        notion_db_id="db1",
        title_field="Title",
        due_date_field="Due",
        duration_field="Duration"
    )

    mapping_repository.save(db_session, field_mapping)

    retrieved = db_session.query(FieldMapping).filter_by(user_id=user.id, notion_db_id="db1").first()

    assert retrieved.title_field == "Title"
    assert retrieved.due_date_field == "Due"
    assert retrieved.duration_field == "Duration"


def test_task_candidate_repository_save(db_session, test_user):
    user, _ = test_user

    task_candidate_repository = TaskCandidateRepository()

    task_candidate = TaskCandidate(user_id=user.id, notion_db_id="db1", title="Test Task", confidence=0.9)

    task_candidate_repository.save_candidates(db_session, [task_candidate])

    retrieved_candidate = db_session.query(TaskCandidate).filter_by(user_id=user.id).first()

    assert retrieved_candidate.title == "Test Task"
    assert retrieved_candidate.confidence == 0.9


def test_task_candidate_repository_get(db_session, test_user):
    user, _ = test_user

    task_candidate_factory = TaskCandidateRepository()

    task_candidate = TaskCandidate(user_id=user.id, notion_db_id="db1", title="Test Task", confidence=0.9)
    db_session.add(task_candidate)
    db_session.commit()

    retrieved_candidates = task_candidate_factory.get_candidates(db_session, user.id, "db1")

    assert len(retrieved_candidates) == 1
    assert retrieved_candidates[0].title == "Test Task"
