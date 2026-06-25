# app/scripts/upgrade_db.py

"""
Applies all pending Alembic migrations to the configured database.

Typical usage:

    python app/scripts/upgrade_db.py
"""

import logging
import os
import subprocess
import sys

from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)


def upgrade_database() -> None:
    """Apply all pending Alembic migrations."""

    env = os.environ.copy()

    env["FLASK_APP"] = "app"
    env["DATABASE_URL"] = Config.DATABASE_URL

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
    logger.info("Database upgraded successfully.")


if __name__ == "__main__":
    upgrade_database()