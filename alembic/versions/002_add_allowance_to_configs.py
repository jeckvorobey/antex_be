"""Add allowance column to Configs table.

Revision ID: 002
Revises: 001
Create Date: 2026-04-03 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "Configs",
        sa.Column("allowance", sa.Float(), nullable=False, server_default="2.0"),
    )


def downgrade() -> None:
    op.drop_column("Configs", "allowance")
