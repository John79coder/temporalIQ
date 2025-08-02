import os
import logging
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default test DB URL (you can override via env var)
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/testdb")
DB_USER = "postgres"
DB_PASS = "postgres"
DB_HOST = "localhost"
DB_PORT = 5432

def extract_db_name_and_base_url(full_url: str):
    parts = full_url.rsplit("/", 1)
    db_name = parts[-1]
    base_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/postgres"
    return db_name, base_url

def recreate_database():
    db_name, base_url = extract_db_name_and_base_url(TEST_DB_URL)

    logger.info(f"🔌 Connecting to PostgreSQL at {base_url}")
    try:
        conn = psycopg2.connect(base_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        logger.info(f"⚠️ Terminating active connections to {db_name}")
        cursor.execute(f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid();
        """, (db_name,))

        logger.info(f"🧨 Dropping database {db_name} (if exists)")
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")

        logger.info(f"✅ Creating database {db_name}")
        cursor.execute(f"CREATE DATABASE {db_name}")

        cursor.close()
        conn.close()

        logger.info(f"🎯 Test database {db_name} is ready.")
    except Exception as e:
        logger.error("❌ Failed to create test database", exc_info=e)
        raise

if __name__ == "__main__":
    recreate_database()
