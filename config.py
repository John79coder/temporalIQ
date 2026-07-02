# config.py
import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

class Config:
    TESTING = False
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/appdb")
    if os.getenv("TEST_DATABASE_URL") == DATABASE_URL:
        raise ValueError("Production and test database URLs must be distinct")
    SECRET_KEY = os.environ["SECRET_KEY"]
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", "24"))
    SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
    NOTION_CLIENT_ID = os.getenv("NOTION_CLIENT_ID")
    NOTION_CLIENT_SECRET = os.getenv("NOTION_CLIENT_SECRET")
    NOTION_REDIRECT_URI = os.getenv("NOTION_REDIRECT_URI")
    APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID")
    DEFAULT_WORK_HOURS_PER_DAY = float(os.getenv("DEFAULT_WORK_HOURS_PER_DAY", "7.6"))
    DEFAULT_BLOCK_MINUTES = int(os.getenv("DEFAULT_BLOCK_MINUTES", "30"))
    DEFAULT_MAX_BLOCKS_PER_DAY = int(os.getenv("DEFAULT_MAX_BLOCKS_PER_DAY", "16"))
    INCLUDE_WEEKENDS = bool(int(os.getenv("INCLUDE_WEEKENDS", "0")))
    ENCRYPTION_KEY = os.environ["ENCRYPTION_KEY"]
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
    STRIPE_PRICE_ID_PREMIUM = os.getenv("STRIPE_PRICE_ID_PREMIUM")
    MODEL_DIR = os.getenv("MODEL_DIR", "ai_models_cache")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    SESSION_TYPE = "filesystem"
    SESSION_FILE_DIR = os.path.join(tempfile.gettempdir(), "flask_session")
    SESSION_PERMANENT = True
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    LOG_FILE_PATH = os.path.join(PROJECT_ROOT, 'log.txt')
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "False").lower() == "true"
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "no-reply@example.com")

    JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", "24"))
    JWT_REFRESH_EXP_DAYS = int(os.getenv("JWT_REFRESH_EXP_DAYS", "30"))

    JWT_REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY", os.environ["JWT_SECRET_KEY"])

    AUTH_COOKIE_NAME = "auth_token"
    REFRESH_COOKIE_NAME = "refresh_token"
    CSRF_COOKIE_NAME = "csrf_token"
    AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "Lax")
    AUTH_COOKIE_DOMAIN = os.getenv("AUTH_COOKIE_DOMAIN") or None
    # Default True (prod). Override to False in dev/.env if you're testing over
    # plain http — browsers silently drop Secure cookies on non-https origins.
    AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "True").lower() == "true"

class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/testdb")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
    JWT_ALGORITHM = "HS256"
    JWT_TOKEN_LOCATION = ["headers"]
    SECRET_KEY = os.environ["SECRET_KEY"]
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    RATELIMIT_STORAGE_URI = "memory://"
    ENCRYPTION_KEY = os.environ["ENCRYPTION_KEY"]
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

    AUTH_COOKIE_SECURE = False  # test client runs over plain http
    JWT_REFRESH_SECRET_KEY = os.environ["JWT_SECRET_KEY"]