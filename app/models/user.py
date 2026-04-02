"""Модель пользователя."""
# ruff: noqa: N815

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.city import City
    from app.models.order import Order


class User(Base, TimestampMixin):
    __tablename__ = "Users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    session: Mapped[str | None] = mapped_column(Text, nullable=True)
    chatId: Mapped[int | None] = mapped_column("chatId", BigInteger, nullable=True)
    role: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("Cities.id"), nullable=True)

    orders: Mapped[list[Order]] = relationship("Order", back_populates="user")
    city: Mapped[City | None] = relationship("City", back_populates="users")
