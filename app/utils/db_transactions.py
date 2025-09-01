# app/utils/db_tx.py
from functools import wraps
from flask import g
from sqlalchemy.orm import Session
from app.extensions import db  # your Flask-SQLAlchemy instance

def _in_tx(session: Session) -> bool:
    """Version-safe check for an active transaction on this session."""
    try:
        # SQLAlchemy 1.4/2.x
        return session.in_transaction() is not None
    except AttributeError:
        getter = getattr(session, "get_transaction", None)
        return getter() is not None if callable(getter) else False

def transactional_route(param_name: str = "db"):
    """
    Wrap a Flask route so it runs inside a single transaction.
    - Injects the Session into the route via kwarg `param_name` (default "db").
    - If a transaction is already open, it won't open another.
    - Scoped session cleanup is handled by Flask/Flask-SQLAlchemy at teardown.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            session = kwargs.get(param_name) or db.session
            kwargs[param_name] = session
            g.db = session  # optional convenience

            if _in_tx(session):
                return fn(*args, **kwargs)

            with session.begin():  # one TX for the whole handler
                return fn(*args, **kwargs)
        return wrapper
    return decorator
