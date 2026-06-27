"""
tests/conftest.py — Shared pytest fixtures.

Spins up an in-memory SQLite database (not the real PostgreSQL), creates the
schema from the ORM models, and overrides the ``get_db`` dependency so every
request in a test uses the same isolated DB.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (register all tables on Base.metadata)
from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client():
    # In-memory SQLite shared across threads/connections for the test's lifetime.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
