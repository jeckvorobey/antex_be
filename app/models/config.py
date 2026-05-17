"""Модель конфигурации (id=1, всегда единственная запись)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Config(Base, TimestampMixin):
    __tablename__ = "Configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
