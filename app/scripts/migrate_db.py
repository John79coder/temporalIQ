# app/scripts/migrate_db.py

"""
Generates a new Alembic migration.

Run this script only after changing SQLAlchemy models.

Review the generated migration before applying it.

Typical usage:

    python -m app.scripts.migrate_db
    python -m app.scripts.migrate_db "Initial schema"
    python -m app.scripts.migrate_db "Add UserTwoFactor table"
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


def generate_migration(message: str = "Auto migration") -> None:
    """Generate a new Alembic migration."""

    env = os.environ.copy()

    env["FLASK_APP"] = "main"
    env["DATABASE_URL"] = Config.DATABASE_URL

    logger.info(f"Generating Alembic migration: {message}")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flask",
            "db",
            "migrate",
            "-m",
            message,
        ],
        env=env,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        logger.error(result.stderr)
        raise RuntimeError("Migration generation failed.")

    if result.stdout:
        print("STDOUT:")
        print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    logger.info("Migration generated successfully.")


if __name__ == "__main__":
    message = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Auto migration"
    )

    generate_migration(message)