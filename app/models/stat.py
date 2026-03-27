"""Модель статистики действий пользователя."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Stat(Base, TimestampMixin):
    __tablename__ = "Stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserId: Mapped[int] = mapped_column("UserId", BigInteger, ForeignKey("Users.id"), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trigger: Mapped[str] = mapped_column(String(100), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="stats")
