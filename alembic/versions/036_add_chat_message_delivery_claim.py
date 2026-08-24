"""Добавить lease доставки текстовых сообщений manager chat.

Revision ID: 036
Revises: 035
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ChatMessages",
        sa.Column("delivery_claim_token", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ChatMessages",
        sa.Column("delivery_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ChatMessages", "delivery_claimed_at")
    op.drop_column("ChatMessages", "delivery_claim_token")
