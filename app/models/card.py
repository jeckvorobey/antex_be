"""Модель карты."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order


class Card(Base, TimestampMixin):
    __tablename__ = "Cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bank: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    number: Mapped[str] = mapped_column(String(255), nullable=False)
    isActive: Mapped[bool] = mapped_column("isActive", Boolean, default=True, nullable=False)

    orders: Mapped[list[Order]] = relationship("Order", back_populates="card")
