"""Модель банка."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.bank_account import BankAccount
    from app.models.limitation import Limitation
    from app.models.order import Order


class Bank(Base, TimestampMixin):
    __tablename__ = "Banks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    orders: Mapped[list[Order]] = relationship("Order", back_populates="bank")
    bank_accounts: Mapped[list[BankAccount]] = relationship("BankAccount", back_populates="bank")
    limitation: Mapped[Limitation | None] = relationship("Limitation", back_populates="bank", uselist=False)
