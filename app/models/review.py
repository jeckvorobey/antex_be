"""Модель отзыва."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order


class Review(Base, TimestampMixin):
    __tablename__ = "Reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    OrderId: Mapped[int] = mapped_column("OrderId", Integer, ForeignKey("Orders.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    fromChatId: Mapped[int] = mapped_column("fromChatId", BigInteger, nullable=False)
    msgId: Mapped[int] = mapped_column("msgId", Integer, nullable=False)
    publish: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    order: Mapped[Order] = relationship("Order", back_populates="review")
