# tests/migration/test_migration.py
from unittest.mock import patch
from app import create_app
from config import TestingConfig

from tests.conftest import app

import pytest

from sqlalchemy.exc import IntegrityError
from app.scheduling.models.entities import Task
from app.auth.models.entities import User


import os
import logging
import traceback
from flask import current_app
from app.extensions import db

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)





# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# File handler
log_file_path = os.path.join(os.path.dirname(__file__), "migration_test.log")
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

def _test_alembic_migrations_apply_cleanly(app):
    root_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(root_dir, "..", ".."))
    os.chdir(project_root)

    logger.info("Starting Alembic migration test...")
    logger.info(f"Changed working directory to: {project_root}")

    try:
        with app.app_context():
            db_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "N/A")
            logger.info(f"SQLAlchemy database URI: {db_uri}")

            logger.info("Dropping all tables from test database...")
            db.drop_all()

            logger.info("Creating Flask CLI test runner...")
            runner = app.test_cli_runner()

            logger.info("Running 'flask db upgrade' migration...")
            try:
                result = runner.invoke(args=["db", "upgrade"], catch_exceptions=False)
            except Exception as e:
                logger.exception("Exception occurred while running migration command.")
                raise

            logger.info("Migration command executed.")
            logger.info(f"stdout:\n{result.output}")
            logger.info(f"stderr:\n{result.stderr}")
            logger.info(f"exit_code: {result.exit_code}")
            logger.info(f"exception: {result.exception}")

            assert result.exit_code == 0, f"Migration failed: {result.output}"

            logger.info("Reflecting current database schema...")
            db.reflect()
            tables = db.metadata.tables.keys()
            logger.info(f"Reflected tables: {list(tables)}")

            expected_tables = [
                "users",
                "notion_connections",
                "field_mappings",
                "task_candidates",
                "notion_feedback_logs",
                "icloud_connections",
                "icloud_calendar_selections",
                "tasks",
                "time_blocks",
                "user_preferences",
                "verification_tokens",
            ]

            for table in expected_tables:
                logger.info(f"Checking for expected table: '{table}'")
                assert table in tables, f"Missing table: {table}"

            logger.info("✅ All expected tables found in test database.")

    except Exception as e:
        logger.error("❌ Test failed with an exception:")
        traceback.print_exc()
        raise  # Preserve traceback in pytest


def test_database_schema_matches_models(app):
    with app.app_context():
        db.reflect()
        model_tables = set(db.Model.metadata.tables.keys())
        db_tables = set(db.metadata.tables.keys())
        assert model_tables == db_tables

def test_foreign_key_integrity_task_user(db_session):
    task = Task(notion_db_id="db1", title="Test")
    db_session.add(task)
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()

def test_unique_user_email_constraint(db_session):
    user1 = User(email="dup@example.com", hashed_password="hash")
    db_session.add(user1)
    db_session.commit()
    user2 = User(email="dup@example.com", hashed_password="hash")
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()

import subprocess
@patch("subprocess.run")
def test_database_migration_application(mock_run):
    app = create_app(TestingConfig)
    with app.app_context():
        mock_run.side_effect = lambda *args, **kwargs: subprocess.CompletedProcess(args, 0)
        from app.scripts.migrate_db import run_migration
        run_migration(TestingConfig, "test", TestingConfig.SQLALCHEMY_DATABASE_URI)
        assert mock_run.call_count >= 2  # migrate and upgrade
        assert any(' '.join(call[0][0][:3]) == "flask db migrate" for call in mock_run.call_args_list)
        assert any(' '.join(call[0][0][:3]) == "flask db upgrade" for call in mock_run.call_args_list)