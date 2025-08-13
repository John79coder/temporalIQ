# app/scripts/init_db.py
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
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(project_root)
logger.info(f"Added project root to sys.path: {project_root}")

from app import create_app
from app.extensions import db
from config import Config


def create_database_if_not_exists(db_url):
    """Create the PostgreSQL database if it doesn't exist."""
    db_name = db_url.split("/")[-1]
    base_url = "/".join(db_url.split("/")[:-1]) + "/postgres"
    try:
        logger.info(f"Connecting to PostgreSQL server at {base_url}")
        conn = psycopg2.connect(base_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        logger.info(f"Terminating open connections to database {db_name}")
        cursor.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{db_name}' AND pid <> pg_backend_pid();
        """)
        logger.info(f"Dropping database {db_name} if it exists")
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")
        logger.info(f"Creating database {db_name}")
        cursor.execute(f"CREATE DATABASE {db_name}")
        cursor.close()
        conn.close()
        logger.info(f"Successfully created database: {db_name}")
    except Exception as e:
        logger.error(f"Failed to create database: {e}")
        raise


app = create_app(Config)

with app.app_context():
    try:
        logger.info("Initializing production database")
        create_database_if_not_exists(Config.DATABASE_URL)
        logger.info("Creating database schema")
        db.create_all()
        logger.info("Production database tables initialized successfully")
    except OperationalError as e:
        logger.error(f"Failed to initialize tables: {e}")
        raise
