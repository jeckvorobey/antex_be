"""Модель лимитов банка."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.bank import Bank


class Limitation(Base, TimestampMixin):
    __tablename__ = "Limitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BankId: Mapped[int] = mapped_column("BankId", Integer, ForeignKey("Banks.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, default=50000, nullable=False)
    baseAmount: Mapped[int] = mapped_column("baseAmount", Integer, default=50000, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True)
    isActive: Mapped[bool] = mapped_column("isActive", Boolean, default=True, nullable=False)

    bank: Mapped[Bank] = relationship("Bank", back_populates="limitation")
