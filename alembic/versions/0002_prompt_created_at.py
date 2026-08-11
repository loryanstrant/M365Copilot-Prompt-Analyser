"""add created_at to prompts

Adds a full timestamp column to ``prompts`` (used to order the per-conversation
prompt thread) and backfills it for existing rows from ``raw_json.createdDateTime``.

Revision ID: 0002_prompt_created_at
Revises: 0001_initial
Create Date: 2026-08-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_prompt_created_at"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill existing rows from the raw Graph payload (Postgres JSONB path).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE prompts
            SET created_at = (raw_json->>'createdDateTime')::timestamptz
            WHERE created_at IS NULL
              AND raw_json ? 'createdDateTime'
              AND (raw_json->>'createdDateTime') <> ''
            """
        )


def downgrade() -> None:
    op.drop_column("prompts", "created_at")
