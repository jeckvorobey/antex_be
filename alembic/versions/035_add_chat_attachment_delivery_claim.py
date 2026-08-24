"""Добавить lease конкурентной доставки вложений manager chat.

Revision ID: 035
Revises: 034
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавить durable token и timestamp межинстансного delivery claim."""
    op.add_column(
        "ChatAttachments",
        sa.Column("delivery_claim_token", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ChatAttachments",
        sa.Column("delivery_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Удалить delivery lease metadata."""
    op.drop_column("ChatAttachments", "delivery_claimed_at")
    op.drop_column("ChatAttachments", "delivery_claim_token")
