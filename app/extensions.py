# app/extensions.py
from flask import current_app
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_caching import Cache
import os

from sqlalchemy.dialects.postgresql.json import JSONB

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

mail = Mail()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=redis_url,
)

db = SQLAlchemy()

db.JSONB = JSONB

csrf = CSRFProtect()
csrf_exempt = csrf.exempt

cache = Cache(config={
    "CACHE_TYPE": "flask_caching.backends.RedisCache" if os.getenv("FLASK_ENV") != "test" else "flask_caching.backends.SimpleCache",
    "CACHE_REDIS_URL": redis_url,
    "CACHE_DEFAULT_TIMEOUT": 3600  # Default TTL: 1 hour
})

def limit(default):
    def _limit():
        if current_app and current_app.config.get("TESTING"):
            return "1000 per minute"
        return default
    return _limit