"""Добавить постоянные чаты менеджера и аудит сообщений.

Revision ID: 031
Revises: 030
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ChatConversations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("unread_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["Users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_chat_conversations_user_id"),
    )
    op.create_index(
        "ix_chat_conversations_last_message_at",
        "ChatConversations",
        ["last_message_at"],
    )
    op.create_index(
        "ix_chat_conversations_unread_count",
        "ChatConversations",
        ["unread_count"],
    )

    op.create_table(
        "ChatMessages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("message_type", sa.String(length=16), server_default="text", nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_edit_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_status", sa.String(length=16), server_default="received", nullable=False),
        sa.Column("client_request_id", sa.String(length=64), nullable=True),
        sa.Column("reply_to_message_id", sa.Integer(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["ChatConversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reply_to_message_id"], ["ChatMessages.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "telegram_chat_id",
            "telegram_message_id",
            name="uq_chat_messages_telegram_identity",
        ),
        sa.UniqueConstraint("client_request_id", name="uq_chat_messages_client_request_id"),
    )
    op.create_index(
        "ix_chat_messages_conversation_id_id",
        "ChatMessages",
        ["conversation_id", "id"],
    )
    op.create_index(
        "ix_chat_messages_delivery_status",
        "ChatMessages",
        ["delivery_status"],
    )

    op.create_table(
        "ChatMessageRevisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("old_text", sa.Text(), nullable=True),
        sa.Column("new_text", sa.Text(), nullable=True),
        sa.Column("telegram_edit_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["ChatMessages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "message_id",
            "revision",
            name="uq_chat_message_revision_number",
        ),
    )

    op.create_table(
        "ChatAttachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("telegram_file_id", sa.Text(), nullable=False),
        sa.Column("telegram_file_unique_id", sa.Text(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["ChatMessages.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chat_attachments_message_id", "ChatAttachments", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_attachments_message_id", table_name="ChatAttachments")
    op.drop_table("ChatAttachments")
    op.drop_table("ChatMessageRevisions")
    op.drop_index("ix_chat_messages_delivery_status", table_name="ChatMessages")
    op.drop_index("ix_chat_messages_conversation_id_id", table_name="ChatMessages")
    op.drop_table("ChatMessages")
    op.drop_index("ix_chat_conversations_unread_count", table_name="ChatConversations")
    op.drop_index("ix_chat_conversations_last_message_at", table_name="ChatConversations")
    op.drop_table("ChatConversations")
