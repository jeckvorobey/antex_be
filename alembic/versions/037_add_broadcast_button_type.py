"""Добавить тип кнопки Telegram-рассылки.

Revision ID: 037
Revises: 036
"""

import sqlalchemy as sa

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет безопасное значение url для всех существующих рассылок."""
    op.add_column(
        "Broadcasts",
        sa.Column(
            "button_type",
            sa.String(length=16),
            server_default="url",
            nullable=False,
            comment="Тип кнопки рассылки: обычная URL-ссылка или Telegram web_app",
        ),
    )


def downgrade() -> None:
    """Удаляет тип кнопки рассылки."""
    op.drop_column("Broadcasts", "button_type")
