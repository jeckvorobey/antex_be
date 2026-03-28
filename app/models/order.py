"""Модель заявки на обмен (paranoid: soft delete через destroyTime)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.bank import Bank
    from app.models.bank_account import BankAccount
    from app.models.card import Card
    from app.models.review import Review
    from app.models.user import User


class Order(Base, TimestampMixin):
    __tablename__ = "Orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserId: Mapped[int] = mapped_column("UserId", BigInteger, ForeignKey("Users.id"), nullable=False)
    BankId: Mapped[int] = mapped_column("BankId", Integer, ForeignKey("Banks.id"), nullable=False)
    CardId: Mapped[int | None] = mapped_column("CardId", Integer, ForeignKey("Cards.id"), nullable=True)
    currencySell: Mapped[str] = mapped_column("currencySell", String(20), nullable=False)
    amountSell: Mapped[int] = mapped_column("amountSell", Integer, nullable=False)
    currencyBuy: Mapped[str] = mapped_column("currencyBuy", String(20), nullable=False)
    amountBuy: Mapped[float] = mapped_column("amountBuy", Float, nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contactTelegram: Mapped[str | None] = mapped_column("contactTelegram", String(255), nullable=True)
    methodGet: Mapped[str | None] = mapped_column("methodGet", String(20), nullable=True)
    endTime: Mapped[datetime | None] = mapped_column("endTime", DateTime(timezone=True), nullable=True)
    # paranoid soft delete (Sequelize deletedAt='destroyTime')
    destroyTime: Mapped[datetime | None] = mapped_column("destroyTime", DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="orders")
    bank: Mapped[Bank] = relationship("Bank", back_populates="orders")
    card: Mapped[Card | None] = relationship("Card", back_populates="orders")
    bank_account: Mapped[BankAccount | None] = relationship("BankAccount", back_populates="order", uselist=False)
    review: Mapped[Review | None] = relationship("Review", back_populates="order", uselist=False)
