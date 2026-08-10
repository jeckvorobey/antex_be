"""Модель курса валют."""

from __future__ import annotations

from sqlalchemy import Boolean, Enum, Float, Integer, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.enums.country import Country
from app.models.base import Base, TimestampMixin


class Rate(Base, TimestampMixin):
    """Рыночный курс внешней или скрытой внутренней валютной пары."""

    __tablename__ = "Rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    currency: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    margin: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    country: Mapped[Country | None] = mapped_column(
        Enum(
            Country,
            name="country_enum",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=True,
    )
    is_internal: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    display_reversed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
