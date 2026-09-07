"""Сохраняет источник нативной пересылки сообщений.

Revision ID: 040
Revises: 039
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ChatMessages", sa.Column("forward_source_message_id", sa.Integer(), nullable=True)
    )
    op.add_column("ChatMessages", sa.Column("forward_source_label", sa.String(255), nullable=True))
    op.create_foreign_key(
        "fk_chat_messages_forward_source",
        "ChatMessages",
        "ChatMessages",
        ["forward_source_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_chat_messages_forward_source", "ChatMessages", type_="foreignkey")
    op.drop_column("ChatMessages", "forward_source_label")
    op.drop_column("ChatMessages", "forward_source_message_id")
