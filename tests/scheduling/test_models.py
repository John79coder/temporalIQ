# tests/scheduling/test_models.py
from datetime import datetime, timezone

import pytest
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError

from app.auth.models.entities import User
from app.scheduling.models.entities import Task, TimeBlock

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def test_task_creation(db_session):
    user = User(email="test@example.com", hashed_password=pwd_context.hash("Secure123!"))
    db_session.add(user)
    db_session.commit()
    task = Task(
        user_id=user.id,
        notion_db_id="db1",
        title="Test Task",
        due_date="2023-10-10",
        duration=30,
        priority="high",
        status="todo"
    )
    db_session.add(task)
    db_session.commit()
    retrieved = db_session.query(Task).filter_by(user_id=user.id).first()
    assert retrieved.title == "Test Task"
    assert retrieved.notion_db_id == "db1"
    assert retrieved.duration == 30
    assert retrieved.priority == "high"
    assert retrieved.status == "todo"


def test_time_block_creation(db_session):
    user = User(email="test@example.com", hashed_password=pwd_context.hash("Secure123!"))
    db_session.add(user)
    db_session.commit()
    task = Task(user_id=user.id, notion_db_id="db1", title="Test Task")
    db_session.add(task)
    db_session.commit()
    time_block = TimeBlock(
        user_id=user.id,
        calendar_id="cal1",
        start=datetime(2023, 10, 10, 10, 0, tzinfo=timezone.utc),
        end=datetime(2023, 10, 10, 11, 0, tzinfo=timezone.utc),
        task_id=task.id
    )
    db_session.add(time_block)
    db_session.commit()
    retrieved = db_session.query(TimeBlock).filter_by(user_id=user.id).first()
    assert retrieved.calendar_id == "cal1"
    assert retrieved.task_id == task.id


def test_task_missing_required_fields(db_session):
    user = User(email="test@example.com", hashed_password=pwd_context.hash("Secure123!"))
    db_session.add(user)
    db_session.commit()
    task = Task(user_id=user.id)
    db_session.add(task)
    with pytest.raises(IntegrityError, match="not-null constraint"):
        db_session.commit()


def test_time_block_missing_required_fields(db_session):
    user = User(email="test@example.com", hashed_password=pwd_context.hash("Secure123!"))
    db_session.add(user)
    db_session.commit()
    time_block = TimeBlock(user_id=user.id)
    db_session.add(time_block)
    with pytest.raises(IntegrityError, match="not-null constraint"):
        db_session.commit()
