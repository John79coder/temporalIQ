# app/scripts/migrate_db.py
import os
import sys
import logging
import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(project_root)
logger.info(f"Added project root to sys.path: {project_root}")

from app import create_app
from config import Config, TestingConfig

def run_migration(config_class, env_name, db_url):
    """Run Flask-Migrate commands for the specified environment."""
    logger.info(f"Running database migration for {env_name} environment with DB URL: {db_url}")
    app = create_app(config_class)
    with app.app_context():
        try:
            env = os.environ.copy()
            env['FLASK_APP'] = 'app'
            env['DATABASE_URL'] = db_url
            logger.info("Generating migration script")
            result_migrate = subprocess.run(
                ["flask", "db", "migrate", "-m", f"Auto migration for {env_name}"],
                env=env, capture_output=True, text=True
            )
            if result_migrate.returncode != 0:
                logger.error(f"Migration generation failed: {result_migrate.stderr}")
                raise RuntimeError(f"Migration generation failed: {result_migrate.stderr}")
            logger.info("Applying migration")
            result_upgrade = subprocess.run(
                ["flask", "db", "upgrade"],
                env=env, capture_output=True, text=True
            )
            if result_upgrade.returncode != 0:
                logger.error(f"Migration upgrade failed: {result_upgrade.stderr}")
                raise RuntimeError(f"Migration upgrade failed: {result_upgrade.stderr}")
            logger.info(f"Migration complete for {env_name} environment")
        except Exception as e:
            logger.error(f"Migration failed for {env_name}: {e}")
            raise

if __name__ == "__main__":
    run_migration(Config, "production", Config.DATABASE_URL)
    run_migration(TestingConfig, "test", TestingConfig.SQLALCHEMY_DATABASE_URI)