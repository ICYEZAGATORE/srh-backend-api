"""
app/models/knowledge.py — SRH knowledge base entry metadata.

Holds the human-readable content and provenance for each knowledge chunk. The
corresponding vector embeddings live in the external vector DB (Pinecone /
Milvus); this table is the relational source of truth and audit trail.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str | None] = mapped_column(String(5), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    # RAG ingestion fields (migration 0002): trace a row to its vector and make
    # ingestion idempotent via a content hash (unique index).
    pinecone_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    chunk_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<KnowledgeEntry {self.id} topic={self.topic} lang={self.lang}>"
