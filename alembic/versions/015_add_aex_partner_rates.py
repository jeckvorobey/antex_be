"""Add ATXG partner rates table.

Revision ID: 015
Revises: 014
Create Date: 2026-06-26 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "AexPartnerRates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("Users.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("rate", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("AexPartnerRates")
