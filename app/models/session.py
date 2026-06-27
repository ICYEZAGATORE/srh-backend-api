"""
app/models/session.py — Anonymous session.

A session carries NO personally identifying information: no name, email, or
device id. It is a random UUID used only to group a user's queries and
assessments for the duration of their visit (see README "Security Notes").
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base

# JSONB on PostgreSQL, plain JSON elsewhere (e.g. the SQLite test DB).
JSONType = JSON().with_variant(JSONB, "postgresql")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    lang: Mapped[str] = mapped_column(String(5), default="en")
    # e.g. {"screen_reader": true, "high_contrast": false, "tts": true}
    accessibility_prefs: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    queries = relationship("Query", back_populates="session")
    assessments = relationship("Assessment", back_populates="session")

    def __repr__(self) -> str:
        return f"<Session {self.id} lang={self.lang}>"
