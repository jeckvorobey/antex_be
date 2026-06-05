"""Site lead repository."""

from __future__ import annotations

from sqlalchemy import desc, select

from app.models.site_lead import SiteLead
from app.repositories.base import BaseRepository


class SiteLeadRepository(BaseRepository[SiteLead]):
    model = SiteLead

    async def list_all(self) -> list[SiteLead]:
        result = await self.session.execute(select(SiteLead).order_by(desc(SiteLead.createdAt)))
        return list(result.scalars().all())
