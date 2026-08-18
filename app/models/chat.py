"""Persistent manager chat models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ChatConversation(Base, TimestampMixin):
    __tablename__ = "ChatConversations"
    __table_args__ = (
        Index("ix_chat_conversations_last_message_at", "last_message_at"),
        Index("ix_chat_conversations_unread_count", "unread_count"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("Users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default="open",
        server_default="open",
        nullable=False,
    )
    unread_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_outbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User")
    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "ChatMessages"
    __table_args__ = (
        UniqueConstraint(
            "telegram_chat_id",
            "telegram_message_id",
            name="uq_chat_messages_telegram_identity",
        ),
        Index("ix_chat_messages_conversation_id_id", "conversation_id", "id"),
        Index("ix_chat_messages_delivery_status", "delivery_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ChatConversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(16), default="text", nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_edit_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_status: Mapped[str] = mapped_column(
        String(16),
        default="received",
        server_default="received",
        nullable=False,
    )
    client_request_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    reply_to_message_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ChatMessages.id", ondelete="SET NULL"),
        nullable=True,
    )

    conversation: Mapped[ChatConversation] = relationship(
        "ChatConversation",
        back_populates="messages",
    )
    revisions: Mapped[list[ChatMessageRevision]] = relationship(
        "ChatMessageRevision",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ChatMessageRevision.revision",
    )
    attachments: Mapped[list[ChatAttachment]] = relationship(
        "ChatAttachment",
        back_populates="message",
        cascade="all, delete-orphan",
    )


class ChatMessageRevision(Base, TimestampMixin):
    __tablename__ = "ChatMessageRevisions"
    __table_args__ = (
        UniqueConstraint("message_id", "revision", name="uq_chat_message_revision_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ChatMessages.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    old_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_edit_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    message: Mapped[ChatMessage] = relationship("ChatMessage", back_populates="revisions")


class ChatAttachment(Base, TimestampMixin):
    __tablename__ = "ChatAttachments"
    __table_args__ = (Index("ix_chat_attachments_message_id", "message_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ChatMessages.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    telegram_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_file_unique_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    media_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    delivery_claim_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delivery_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    message: Mapped[ChatMessage] = relationship("ChatMessage", back_populates="attachments")
