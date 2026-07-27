"""Async repositories маркетингового домена."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing import MarketingAttribution, MarketingCampaign


class MarketingRepository:
    """Доступ к компаниям и first-touch атрибуциям."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_campaign_by_code(self, code: str) -> MarketingCampaign | None:
        result = await self.session.execute(
            select(MarketingCampaign).where(MarketingCampaign.code == code)
        )
        return result.scalar_one_or_none()

    async def campaign_code_exists(self, code: str) -> bool:
        result = await self.session.execute(
            select(MarketingCampaign.id).where(MarketingCampaign.code == code).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_attribution_by_user(self, user_id: int) -> MarketingAttribution | None:
        result = await self.session.execute(
            select(MarketingAttribution).where(MarketingAttribution.user_id == user_id)
        )
        return result.scalar_one_or_none()
