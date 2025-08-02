from flask import Flask
from sqlalchemy.orm import Session
from urllib.parse import urlparse


def get_database_name(obj: Session | Flask) -> str:
    """
    Extract the database name from a SQLAlchemy session or Flask app.

    Args:
        obj: A SQLAlchemy Session or Flask app instance.

    Returns:
        str: The database name from the SQLAlchemy engine's URL.

    Raises:
        ValueError: If the database name cannot be determined.
    """
    if isinstance(obj, Session):
        if obj.bind is None:
            raise ValueError("Session is not bound to an engine")
        db_url = str(obj.bind.url)
    elif isinstance(obj, Flask):
        db_url = obj.config.get("SQLALCHEMY_DATABASE_URI")
        if not db_url:
            raise ValueError("SQLALCHEMY_DATABASE_URI not set in app config")
    else:
        raise ValueError("Input must be a SQLAlchemy Session or Flask app")

    parsed_url = urlparse(db_url)
    db_name = parsed_url.path.lstrip('/')
    if not db_name:
        raise ValueError("Could not extract database name from URL")
    return db_name