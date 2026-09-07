"""Задание синхронизации Telegram-представления заявки."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class OrderTelegramSyncTask(Base, TimestampMixin):
    """Надёжно доставляет одно представление статуса одному Telegram-target."""

    __tablename__ = "OrderTelegramSyncTasks"
    __table_args__ = (
        UniqueConstraint(
            "OrderId",
            "status",
            "target",
            name="uq_order_telegram_sync_task",
        ),
        Index("ix_order_telegram_sync_tasks_due", "state", "nextAttemptAt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    OrderId: Mapped[int] = mapped_column(
        "OrderId",
        Integer,
        ForeignKey("Orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    target: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attemptCount: Mapped[int] = mapped_column(  # noqa: N815
        "attemptCount",
        Integer,
        default=0,
        nullable=False,
    )
    nextAttemptAt: Mapped[datetime] = mapped_column(  # noqa: N815
        "nextAttemptAt",
        DateTime(timezone=True),
        nullable=False,
    )
    lockedAt: Mapped[datetime | None] = mapped_column(  # noqa: N815
        "lockedAt",
        DateTime(timezone=True),
        nullable=True,
    )
    deliveredAt: Mapped[datetime | None] = mapped_column(  # noqa: N815
        "deliveredAt",
        DateTime(timezone=True),
        nullable=True,
    )
    lastErrorCode: Mapped[str | None] = mapped_column(  # noqa: N815
        "lastErrorCode",
        String(64),
        nullable=True,
    )

    order = relationship("Order")
