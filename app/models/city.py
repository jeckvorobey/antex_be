"""Модель города."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums.country import Country
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.user import User


class City(Base, TimestampMixin):
    __tablename__ = "Cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[Country] = mapped_column(
        Enum(
            Country,
            name="country_enum",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )

    users: Mapped[list[User]] = relationship("User", back_populates="city")
    orders: Mapped[list[Order]] = relationship("Order", back_populates="city")
