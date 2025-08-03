# config.py
import os
from cryptography.fernet import Fernet


class Config:
    TESTING = False
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/appdb")
    if os.getenv("TEST_DATABASE_URL") == DATABASE_URL:
        raise ValueError("Production and test database URLs must be distinct")
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", Fernet.generate_key().decode())
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    JWT_SECRET_KEY = os.getenv("JWT_SECRET", "replace-me-in-prod")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", "24"))
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "no-reply@example.com")
    NOTION_CLIENT_ID = os.getenv("NOTION_CLIENT_ID")
    NOTION_CLIENT_SECRET = os.getenv("NOTION_CLIENT_SECRET")
    NOTION_REDIRECT_URI = os.getenv("NOTION_REDIRECT_URI")
    APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID")
    DEFAULT_WORK_HOURS_PER_DAY = float(os.getenv("DEFAULT_WORK_HOURS_PER_DAY", "7.6"))
    DEFAULT_BLOCK_MINUTES = int(os.getenv("DEFAULT_BLOCK_MINUTES", "30"))
    DEFAULT_MAX_BLOCKS_PER_DAY = int(os.getenv("DEFAULT_MAX_BLOCKS_PER_DAY", "16"))
    INCLUDE_WEEKENDS = bool(int(os.getenv("INCLUDE_WEEKENDS", "0")))
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
    STRIPE_PRICE_ID_PREMIUM = os.getenv("STRIPE_PRICE_ID_PREMIUM")
    MODEL_DIR = os.getenv("MODEL_DIR", "ai_models_cache")
    SESSION_TYPE = "filesystem"  # Add this line
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    LOG_FILE_PATH = os.path.join(PROJECT_ROOT, 'log.txt')

class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/testdb")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = "test-secret"
    JWT_ALGORITHM = "HS256"
    JWT_TOKEN_LOCATION = ["headers"]
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", Fernet.generate_key().decode())
    RATELIMIT_STORAGE_URI = "memory://"
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    DEBUG = False
    PROPAGATE_EXCEPTIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }
    STRIPE_SECRET_KEY = "sk_test_..."
    STRIPE_WEBHOOK_SECRET = "whsec_test_..."
    STRIPE_PRICE_ID_PREMIUM = "price_test_..."
    MODEL_DIR = os.getenv("MODEL_DIR", "ai_models_cache_for_testing")
    SESSION_TYPE = "filesystem"  # Add this line