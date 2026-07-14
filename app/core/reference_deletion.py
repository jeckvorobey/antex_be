"""Переиспользуемая политика удаления справочных записей."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class SoftDeletable(Protocol):
    """Контракт записи, которую можно скрыть вместо физического удаления."""

    deleted_at: datetime | None


class ReferenceDeletionService:
    """Удаляет справочник; при связях применяет мягкое удаление."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def delete_or_soft_delete(
        self,
        item: SoftDeletable,
        has_relations: Callable[[], Awaitable[bool]],
    ) -> bool:
        """Удаляет запись; возвращает True, если она скрыта из-за связанных данных."""
        if await has_relations():
            item.deleted_at = datetime.now(UTC)
            await self.session.commit()
            return True
        await self.session.delete(item)
        await self.session.commit()
        return False
