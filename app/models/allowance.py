"""Модель надбавки к курсу."""

from __future__ import annotations

from sqlalchemy import Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Allowance(Base, TimestampMixin):
    __tablename__ = "Allowances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
