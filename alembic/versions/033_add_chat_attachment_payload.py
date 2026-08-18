"""Добавить durable payload исходящих вложений manager chat.

Revision ID: 033
Revises: 032
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Разрешить pending Telegram file id и сохранить bytes в PostgreSQL."""
    op.alter_column(
        "ChatAttachments",
        "telegram_file_id",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.add_column("ChatAttachments", sa.Column("payload", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    """Удалить недоставленные payload и восстановить обязательный Telegram file id."""
    op.execute(sa.text('DELETE FROM "ChatAttachments" WHERE telegram_file_id IS NULL'))
    op.alter_column(
        "ChatAttachments",
        "telegram_file_id",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column("ChatAttachments", "payload")
