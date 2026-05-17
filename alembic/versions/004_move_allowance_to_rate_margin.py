"""Move allowance from Configs to per-rate margin.

Revision ID: 004
Revises: 003
Create Date: 2026-05-17 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "Rates",
        sa.Column("margin", sa.Float(), nullable=False, server_default="3.0"),
    )
    op.execute(sa.text('UPDATE "Rates" SET margin = 3.0 WHERE margin IS NULL'))
    op.drop_column("Configs", "allowance")


def downgrade() -> None:
    op.add_column(
        "Configs",
        sa.Column("allowance", sa.Float(), nullable=False, server_default="2.0"),
    )
    op.drop_column("Rates", "margin")
