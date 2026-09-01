"""Модель пользователя."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums.user import UserRole, has_operator_access
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.aex import AexPartnerRate, AexPersonalRate, AexWallet
    from app.models.city import City
    from app.models.order import Order


class User(Base, TimestampMixin):
    __tablename__ = "Users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    session: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[int] = mapped_column(Integer, default=int(UserRole.USER), nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_write_access: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    city_id: Mapped[int | None] = mapped_column(ForeignKey("Cities.id"), nullable=True)
    language_code_app: Mapped[str] = mapped_column(
        String(10),
        default="ru",
        server_default="ru",
        nullable=False,
    )
    # Реферальная система
    referral_code: Mapped[str | None] = mapped_column(
        String(16),
        unique=True,
        nullable=True,
    )
    lastActiveAt: Mapped[datetime | None] = mapped_column(  # noqa: N815
        "lastActiveAt",
        DateTime(timezone=True),
        nullable=True,
    )

    orders: Mapped[list[Order]] = relationship(
        "Order",
        back_populates="user",
        foreign_keys="Order.UserId",
    )
    city: Mapped[City | None] = relationship("City", back_populates="users")
    aex_wallet: Mapped[AexWallet | None] = relationship(
        "AexWallet",
        back_populates="user",
        uselist=False,
    )
    aex_personal_rate: Mapped[AexPersonalRate | None] = relationship(
        "AexPersonalRate",
        back_populates="user",
        uselist=False,
    )
    aex_partner_rate: Mapped[AexPartnerRate | None] = relationship(
        "AexPartnerRate",
        back_populates="user",
        uselist=False,
    )

    def isManager(self) -> bool:  # noqa: N802
        """Определяет, имеет ли пользователь доступ к manager Mini App."""
        return has_operator_access(self.role)
