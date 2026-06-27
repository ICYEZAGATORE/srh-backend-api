"""initial schema: sessions, queries, assessments, knowledge_entries

Revision ID: 0001
Revises:
Create Date: 2026-06-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# JSONB on PostgreSQL, generic JSON elsewhere (matches the ORM models).
JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=True),
        sa.Column("accessibility_prefs", JSONType, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "queries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        # Anonymised raw text (see app/models/query.py); NULL for discarded unsafe text.
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("lang", sa.String(length=5), nullable=True),
        sa.Column("safe", sa.Boolean(), nullable=True),
        sa.Column("topic", sa.String(length=50), nullable=True),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("fallback", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("responses", JSONType, nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("type IN ('pre', 'post')", name="ck_assessment_type"),
    )

    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("lang", sa.String(length=5), nullable=True),
        sa.Column("topic", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_entries")
    op.drop_table("assessments")
    op.drop_table("queries")
    op.drop_table("sessions")
