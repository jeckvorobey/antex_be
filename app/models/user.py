"""Модель пользователя Telegram."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.stat import Stat


class User(Base, TimestampMixin):
    __tablename__ = "Users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    session: Mapped[str | None] = mapped_column(Text, nullable=True)
    chatId: Mapped[int | None] = mapped_column("chatId", BigInteger, nullable=True)
    role: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    orders: Mapped[list[Order]] = relationship("Order", back_populates="user")
    stats: Mapped[list[Stat]] = relationship("Stat", back_populates="user")
