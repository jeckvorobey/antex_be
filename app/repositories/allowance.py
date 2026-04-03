"""Репозиторий надбавки (allowance) — делегирует к ConfigRepository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.config import ConfigRepository


class AllowanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._config = ConfigRepository(session)

    async def get_value(self) -> float:
        """Возвращает надбавку в процентах (например 2.0 = 2%)."""
        config = await self._config.get_or_create()
        return config.allowance
