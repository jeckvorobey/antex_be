"""Модель заявки."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.city import City
    from app.models.user import User


class Order(Base, TimestampMixin):
    __tablename__ = "Orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserId: Mapped[int] = mapped_column("UserId", Integer, ForeignKey("Users.id"), nullable=False)
    CityId: Mapped[int] = mapped_column("CityId", Integer, ForeignKey("Cities.id"), nullable=False)
    currencySell: Mapped[str] = mapped_column("currencySell", String(20), nullable=False)
    amountSell: Mapped[int] = mapped_column("amountSell", Integer, nullable=False)
    currencyBuy: Mapped[str] = mapped_column("currencyBuy", String(20), nullable=False)
    amountBuy: Mapped[float | None] = mapped_column("amountBuy", Float, nullable=True)
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contactTelegram: Mapped[str | None] = mapped_column(
        "contactTelegram",
        String(255),
        nullable=True,
    )
    methodGet: Mapped[str | None] = mapped_column("methodGet", String(20), nullable=True)
    endTime: Mapped[datetime | None] = mapped_column(
        "endTime",
        DateTime(timezone=True),
        nullable=True,
    )
    # paranoid soft delete (Sequelize deletedAt='destroyTime')
    destroyTime: Mapped[datetime | None] = mapped_column(
        "destroyTime",
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped[User] = relationship("User", back_populates="orders")
    city: Mapped[City] = relationship("City", back_populates="orders")
