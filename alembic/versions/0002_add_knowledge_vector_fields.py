"""add knowledge vector fields: pinecone_id, chunk_hash

Adds two columns to ``knowledge_entries`` to support the RAG ingestion pipeline:
  - ``pinecone_id``  : the id of this chunk's vector in the vector store, so a
                       relational row can be traced to / deleted from the index.
  - ``chunk_hash``   : SHA-256 of the normalised chunk text, used to make
                       ingestion idempotent (a unique index blocks duplicates).

Additive only — does not modify the 0001 migration.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_entries",
        sa.Column("pinecone_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "knowledge_entries",
        sa.Column("chunk_hash", sa.String(length=64), nullable=True),
    )
    # Unique index makes ingestion idempotent (NULLs from pre-existing rows are
    # allowed by both PostgreSQL and SQLite under a UNIQUE index).
    op.create_index(
        "ix_knowledge_entries_chunk_hash",
        "knowledge_entries",
        ["chunk_hash"],
        unique=True,
    )
    op.create_index(
        "ix_knowledge_entries_pinecone_id",
        "knowledge_entries",
        ["pinecone_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_entries_pinecone_id", table_name="knowledge_entries")
    op.drop_index("ix_knowledge_entries_chunk_hash", table_name="knowledge_entries")
    op.drop_column("knowledge_entries", "chunk_hash")
    op.drop_column("knowledge_entries", "pinecone_id")
