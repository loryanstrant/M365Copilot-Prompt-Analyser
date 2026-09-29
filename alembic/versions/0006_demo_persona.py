"""Add app_config.demo_persona_user_id.

Loading demo data binds the local admin account to one of the seeded directory
users, and this is where that binding lives. Without it the personal pages
cannot be reached at all without an Entra sign-in — ``has_personal_view`` needs
a directory identity and the password admin has none — so anyone evaluating the
product with demo data never sees the pages the README advertises.

NULL on upgrade, and set only by an explicit demo seed. It is cleared again when
demo data is cleared, so a tenant that seeds, looks and then clears is left
exactly where it started.

Revision ID: 0006_demo_persona
Revises: 0005_copilot_sku_autodetect
Create Date: 2026-09-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_demo_persona"
down_revision: str | None = "0005_copilot_sku_autodetect"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_config", sa.Column("demo_persona_user_id", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("app_config", "demo_persona_user_id")
