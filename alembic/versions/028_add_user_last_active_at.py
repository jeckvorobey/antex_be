"""Добавить время последней активности пользователя.

Revision ID: 028
Revises: 027
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет nullable timestamp и индекс для оперативной статистики."""
    op.add_column(
        "Users",
        sa.Column("lastActiveAt", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_last_active_at",
        "Users",
        ["lastActiveAt"],
        unique=False,
    )


def downgrade() -> None:
    """Удаляет индекс и поле активности."""
    op.drop_index("ix_users_last_active_at", table_name="Users")
    op.drop_column("Users", "lastActiveAt")
