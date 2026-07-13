"""Add referral program config fields.

Revision ID: 017
Revises: 016
Create Date: 2026-06-28 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "Configs",
        sa.Column(
            "referral_percent",
            sa.Numeric(10, 4),
            nullable=False,
            server_default="0.2",
        ),
    )
    op.add_column(
        "Configs",
        sa.Column(
            "referral_min_withdraw",
            sa.Numeric(18, 6),
            nullable=False,
            server_default="100",
        ),
    )
    op.add_column(
        "Configs",
        sa.Column("referral_max_withdraw", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "Configs",
        sa.Column(
            "aex_rate",
            sa.Numeric(18, 6),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("Configs", "aex_rate")
    op.drop_column("Configs", "referral_max_withdraw")
    op.drop_column("Configs", "referral_min_withdraw")
    op.drop_column("Configs", "referral_percent")
