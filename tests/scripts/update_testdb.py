# tests/init_testdb.py

"""
Recreates the PostgreSQL test database and applies all Alembic migrations.

Typical usage:

    python tests/init_testdb.py
"""

import logging
import os
import subprocess
import sys

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy.engine import make_url

from config import TestingConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)


def recreate_database(database_url: str) -> None:
    """
    Drops and recreates the PostgreSQL test database.

    The database will exist but contain no tables.
    """

    url = make_url(database_url)
    db_name = url.database
    postgres_url = url.set(database="postgres").render_as_string(hide_password=False)

    logger.info("Connecting to PostgreSQL server...")

    connection = psycopg2.connect(postgres_url)
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        with connection.cursor() as cursor:

            logger.info("Closing active connections...")

            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s
                  AND pid <> pg_backend_pid();
                """,
                (db_name,),
            )

            logger.info(f"Dropping database '{db_name}' if it exists...")

            cursor.execute(f'DROP DATABASE IF EXISTS "{db_name}"')

            logger.info(f"Creating database '{db_name}'...")

            cursor.execute(f'CREATE DATABASE "{db_name}"')

    except Exception:
        logger.exception("Failed to recreate test database.")
        raise

    finally:
        connection.close()

    logger.info("Test database successfully created.")


def upgrade_database() -> None:
    """
    Applies all pending Alembic migrations to the test database.
    """

    env = os.environ.copy()

    env["FLASK_APP"] = "main"
    env["DATABASE_URL"] = TestingConfig.SQLALCHEMY_DATABASE_URI

    logger.info("Applying Alembic migrations...")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flask",
            "db",
            "upgrade",
        ],
        env=env,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        logger.error(result.stderr)
        raise RuntimeError("Database upgrade failed.")

    logger.info(result.stdout)
    logger.info("Test database upgraded successfully.")


if __name__ == "__main__":
    recreate_database(TestingConfig.SQLALCHEMY_DATABASE_URI)
    upgrade_database()