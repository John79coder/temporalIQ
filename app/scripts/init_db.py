# app/scripts/init_db.py

"""
Creates (or recreates) the PostgreSQL database.

This script deliberately DOES NOT create any tables.

Schema creation is handled exclusively by Alembic migrations.

Typical usage:

    python app/scripts/init_db.py

followed by

    python app/scripts/upgrade_db.py
"""

import logging

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy.engine import make_url

from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)


def create_database(database_url: str) -> None:
    """
    Drops and recreates the target PostgreSQL database.

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
        logger.exception("Database creation failed.")
        raise

    finally:
        connection.close()

    logger.info("Database successfully created.")


if __name__ == "__main__":
    create_database(Config.DATABASE_URL)