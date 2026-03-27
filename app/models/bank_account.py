"""Модель банковского счёта (реквизиты для перевода)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.bank import Bank
    from app.models.order import Order


class BankAccount(Base, TimestampMixin):
    __tablename__ = "BankAccounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BankId: Mapped[int] = mapped_column("BankId", Integer, ForeignKey("Banks.id"), nullable=False)
    OrderId: Mapped[int] = mapped_column("OrderId", Integer, ForeignKey("Orders.id"), nullable=False)
    account: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)

    bank: Mapped[Bank] = relationship("Bank", back_populates="bank_accounts")
    order: Mapped[Order] = relationship("Order", back_populates="bank_account")
