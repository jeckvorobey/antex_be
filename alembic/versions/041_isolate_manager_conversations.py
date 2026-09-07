"""Изолировать переписку по паре менеджер-клиент без передачи старой истории.

Revision ID: 041
Revises: 040
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Сохраняет старые чаты без владельца; новые пары имеют независимую историю."""
    op.add_column("ChatConversations", sa.Column("manager_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_chat_conversations_manager",
        "ChatConversations",
        "Users",
        ["manager_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_chat_conversations_user_id", "ChatConversations", type_="unique")
    op.create_unique_constraint(
        "uq_chat_conversations_manager_user",
        "ChatConversations",
        ["manager_id", "user_id"],
    )
    op.create_index(
        "uq_chat_conversations_unowned_user",
        "ChatConversations",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("manager_id IS NULL"),
    )


def downgrade() -> None:
    """Отказывается сливать разные переписки; при конфликте транзакция откатывается."""
    # Создание прежней уникальности намеренно падает, если уже есть разные пары клиента.
    # История не удаляется и не смешивается ради технического rollback.
    op.create_unique_constraint("uq_chat_conversations_user_id", "ChatConversations", ["user_id"])
    op.drop_index("uq_chat_conversations_unowned_user", table_name="ChatConversations")
    op.drop_constraint("uq_chat_conversations_manager_user", "ChatConversations", type_="unique")
    op.drop_constraint("fk_chat_conversations_manager", "ChatConversations", type_="foreignkey")
    op.drop_column("ChatConversations", "manager_id")
