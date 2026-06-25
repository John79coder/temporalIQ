import logging
import os
import sys

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy.exc import OperationalError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)
logger.info(f"Added project root to sys.path: {project_root}")

from app import create_app
from app.extensions import db
from config import TestingConfig


def recreate_database(db_url: str):
    """Drop and recreate the PostgreSQL test database."""
    db_name = db_url.split("/")[-1]
    base_url = "/".join(db_url.split("/")[:-1]) + "/postgres"

    logger.info(f"Connecting to PostgreSQL at {base_url}")

    try:
        conn = psycopg2.connect(base_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        logger.info(f"Terminating active connections to {db_name}")
        cursor.execute(
            """
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = %s
              AND pid <> pg_backend_pid();
            """,
            (db_name,),
        )

        logger.info(f"Dropping database {db_name}")
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")

        logger.info(f"Creating database {db_name}")
        cursor.execute(f"CREATE DATABASE {db_name}")

        cursor.close()
        conn.close()

        logger.info(f"Successfully recreated test database {db_name}")

    except Exception:
        logger.exception("Failed to recreate test database")
        raise


app = create_app(TestingConfig)

with app.app_context():
    try:
        logger.info("Initializing test database")

        recreate_database(TestingConfig.SQLALCHEMY_DATABASE_URI)

        logger.info("Creating database schema")

        db.create_all()

        logger.info("Test database tables initialized successfully")

    except OperationalError:
        logger.exception("Failed to initialize test database")
        raise