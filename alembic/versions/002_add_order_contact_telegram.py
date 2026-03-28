"""Add contactTelegram to Orders.

Revision ID: 002
Revises: 001
Create Date: 2026-03-28 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет поле Telegram-контакта в таблицу заявок."""
    op.add_column("Orders", sa.Column("contactTelegram", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Удаляет поле Telegram-контакта из таблицы заявок."""
    op.drop_column("Orders", "contactTelegram")
