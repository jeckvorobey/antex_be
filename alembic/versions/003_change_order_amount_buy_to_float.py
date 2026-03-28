"""Change Orders.amountBuy to float.

Revision ID: 003
Revises: 002
Create Date: 2026-03-28 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Переводит поле суммы получения на float для дробных USDT-значений."""
    op.alter_column(
        "Orders",
        "amountBuy",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Возвращает поле суммы получения к integer."""
    op.alter_column(
        "Orders",
        "amountBuy",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
