"""Add AEX withdraw limit to config.

Revision ID: 018
Revises: 017
Create Date: 2026-07-06 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет глобальный лимит вывода AEX в singleton config."""
    op.add_column(
        "Configs",
        sa.Column(
            "aex_withdraw_limit",
            sa.Numeric(18, 6),
            nullable=False,
            server_default="100",
        ),
    )


def downgrade() -> None:
    """Удаляет глобальный лимит вывода AEX."""
    op.drop_column("Configs", "aex_withdraw_limit")
