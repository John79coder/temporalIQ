# app/utils/db_transactions.py
from functools import wraps
from flask import g
from sqlalchemy.orm import Session
from app.extensions import db


def _in_tx(session: Session) -> bool:
    """Version-safe check for an active transaction on this session."""
    try:
        return session.in_transaction() is not None  # SA 1.4/2.x
    except AttributeError:
        getter = getattr(session, "get_transaction", None)
        return getter() is not None if callable(getter) else False


def transactional_route(param_name: str = "db"):
    """
    Wrap a Flask route so it runs inside a single transaction.
    - Prefer the request's existing Session (g.db) so we share it with verify_jwt.
    - If a transaction is already open, don't open another.
    - Otherwise, start one with session.begin() for the handler body.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Key change: prefer g.db so we use the SAME Session as verify_jwt
            session = (
                    kwargs.get(param_name)
                    or getattr(g, "db", None)
                    or db.session()  # Create the new session only if needed
            )

            # propagate the chosen session to kwargs and g
            kwargs[param_name] = session
            g.db = session

            # if verify_jwt (or anything earlier) already did a SELECT, a tx may be open
            if _in_tx(session):
                return fn(*args, **kwargs)

            # otherwise, own a single transaction around the handler
            with session.begin():
                result = fn(*args, **kwargs)
                session.commit()  # Explicit commit
                return result

        return wrapper

    return decorator