"""add Kinyarwanda pipeline analytics fields to queries

Adds three columns to ``queries`` for the Kinyarwanda FAQ cache + translate
pipeline. All are analytics/eval flags and are NULL/False for English queries,
so the English request path is unaffected:
  - ``faq_cache_hit``               : the predefined-question FAQ cache served
                                      this turn verbatim.
  - ``low_confidence_translation``  : back-translation QA fell below threshold
                                      (a review flag, not a block).
  - ``pipeline_mode``               : which rw path answered ("native" |
                                      "translate" | "faq"); NULL for English.

Additive only — does not modify earlier migrations.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default keeps the boolean columns non-null for pre-existing rows;
    # nullable pipeline_mode stays NULL for historical (and all English) rows.
    op.add_column(
        "queries",
        sa.Column(
            "faq_cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "queries",
        sa.Column(
            "low_confidence_translation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "queries",
        sa.Column("pipeline_mode", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("queries", "pipeline_mode")
    op.drop_column("queries", "low_confidence_translation")
    op.drop_column("queries", "faq_cache_hit")
