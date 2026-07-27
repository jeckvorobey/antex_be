"""Site lead repository."""

from __future__ import annotations

from sqlalchemy import desc, func, select

from app.models.site_lead import SiteLead
from app.repositories.base import BaseRepository


class SiteLeadRepository(BaseRepository[SiteLead]):
    model = SiteLead

    async def list_all(self) -> list[SiteLead]:
        result = await self.session.execute(select(SiteLead).order_by(desc(SiteLead.createdAt)))
        return list(result.scalars().all())

    async def list_recent(self, *, limit: int = 10) -> list[SiteLead]:
        result = await self.session.execute(
            select(SiteLead).order_by(desc(SiteLead.createdAt)).limit(limit)
        )
        return list(result.scalars().all())

    async def list_paginated(self, *, limit: int, offset: int) -> tuple[list[SiteLead], int]:
        result = await self.session.execute(
            select(SiteLead).order_by(desc(SiteLead.createdAt)).limit(limit).offset(offset)
        )
        total_result = await self.session.execute(select(func.count(SiteLead.id)))
        return list(result.scalars().all()), total_result.scalar_one()
