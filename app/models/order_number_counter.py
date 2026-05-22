"""Годовой счетчик публичных номеров заявок."""
# ruff: noqa: N815

from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrderNumberCounter(Base):
    __tablename__ = "OrderNumberCounters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    lastValue: Mapped[int] = mapped_column("lastValue", Integer, nullable=False, default=0)
