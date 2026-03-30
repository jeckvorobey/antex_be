"""SQLAlchemy-модели рассылок."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    literal_column,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Broadcast(Base, TimestampMixin):
    __tablename__ = "Broadcasts"
    __table_args__ = (
        Index(
            "uq_broadcast_active_singleton",
            literal_column("1"),
            unique=True,
            sqlite_where=text("status IN ('pending', 'running')"),
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Уникальный идентификатор рассылки",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Текущий статус рассылки: pending, running, completed или failed",
    )
    audience_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Тип аудитории, по которой собирались получатели рассылки",
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Исходный текст сообщения, который был задан администратором",
    )
    format: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Формат текста сообщения: plain или html",
    )
    button_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Подпись кнопки под сообщением, если кнопка была задана",
    )
    button_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Ссылка URL или WebApp, которая открывается по кнопке",
    )
    speed_mode_requested: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Запрошенный режим скорости рассылки: free или paid",
    )
    speed_mode_effective: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Фактически использованный режим скорости рассылки",
    )
    target_rps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Целевой лимит сообщений в секунду для данной рассылки",
    )
    worker_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Количество параллельных async worker'ов, отправляющих сообщения",
    )
    total_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Общее количество получателей, попавших в рассылку",
    )
    success_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество успешно доставленных сообщений",
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Количество сообщений, которые не удалось доставить",
    )
    created_by_admin_id: Mapped[int] = mapped_column(
        ForeignKey("Admins.id"),
        nullable=False,
        comment="Идентификатор администратора, который создал рассылку",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время фактического начала отправки рассылки",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время окончания обработки рассылки",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Последняя критическая ошибка, из-за которой рассылка завершилась сбоем",
    )
    createdAt: Mapped[datetime] = mapped_column(  # noqa: N815
        "createdAt",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Время создания записи о рассылке",  # noqa: RUF001
    )
    updatedAt: Mapped[datetime] = mapped_column(  # noqa: N815
        "updatedAt",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Время последнего обновления записи о рассылке",  # noqa: RUF001
    )
