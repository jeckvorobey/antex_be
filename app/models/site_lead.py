"""Site lead model."""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SiteLead(Base, TimestampMixin):
    __tablename__ = "SiteLeads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    messenger: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact: Mapped[str] = mapped_column(String(255), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="antex-landing")
