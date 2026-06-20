"""Базовые SQLAlchemy-модели."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый declarative class."""


class TimestampMixin:
    """Стандартные timestamps проекта."""

    createdAt: Mapped[datetime] = mapped_column(  # noqa: N815
        "createdAt",
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updatedAt: Mapped[datetime] = mapped_column(  # noqa: N815
        "updatedAt",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
