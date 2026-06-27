"""
app/database.py — SQLAlchemy engine, session factory, and declarative Base.

The FastAPI dependency ``get_db`` yields a request-scoped session and always
closes it afterwards.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session as SASession, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# SQLite (used in tests) needs ``check_same_thread=False`` to share a
# connection across the TestClient's threads; PostgreSQL ignores it.
_connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[SASession, None, None]:
    """FastAPI dependency: provide a DB session, closing it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
