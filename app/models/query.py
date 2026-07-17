"""
app/models/query.py — Logged chat queries (safe and unsafe).

PRIVACY NOTE: The ``text`` column stores the raw user message purely for
safety auditing. This is ANONYMISED data — there is no link to any user
identity; a row is only associated with a random, PII-free session UUID.
For UNSAFE queries, the raw text is discarded unless ``LOG_UNSAFE_TEXT=true``
(see app/config.py); in that case only the safety flag/topic is retained.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sessions.id"), nullable=True
    )
    # Anonymised raw text — may be NULL for unsafe queries when LOG_UNSAFE_TEXT=false.
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str | None] = mapped_column(String(5), nullable=True)
    safe: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    topic: Mapped[str | None] = mapped_column(String(50), nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    # ── Kinyarwanda pipeline analytics (NULL/False for English queries) ──────
    # Set when the predefined-question FAQ cache served this turn verbatim
    # (skipping translation + LLM generation).
    faq_cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set in KINYARWANDA_PIPELINE_MODE=translate when the back-translation QA
    # check fell below the similarity threshold — a review flag, not a block.
    low_confidence_translation: Mapped[bool] = mapped_column(Boolean, default=False)
    # Which rw path produced this response ("native" | "translate" | "faq"),
    # for eval/analytics. NULL for English queries.
    pipeline_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session = relationship("Session", back_populates="queries")

    def __repr__(self) -> str:
        return f"<Query {self.id} safe={self.safe} topic={self.topic}>"
