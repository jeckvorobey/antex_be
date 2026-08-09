"""Добавить кэш разрешения Telegram писать пользователю.

Revision ID: 029
Revises: 028
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет безопасное значение false для новых и существующих пользователей."""
    op.add_column(
        "Users",
        sa.Column(
            "telegram_write_access",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Удаляет локальный кэш разрешения Telegram."""
    op.drop_column("Users", "telegram_write_access")
