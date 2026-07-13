"""Сервис маркетинговых кампаний и first-touch атрибуции."""

from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AntExException
from app.models.marketing import MarketingAttribution
from app.modules.marketing.constants import MARKETING_CODE_LENGTH
from app.modules.marketing.repository import MarketingRepository

MARKETING_CODE_PATTERN = re.compile(rf"^[A-Z0-9]{{{MARKETING_CODE_LENGTH}}}$")


class MarketingService:
    """Выполняет неизменяемую first-touch атрибуцию."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = MarketingRepository(session)

    async def attribute_user(self, user_id: int, code: str) -> MarketingAttribution:
        if not MARKETING_CODE_PATTERN.fullmatch(code):
            raise AntExException(
                "Invalid marketing code",
                code="INVALID_MARKETING_CODE",
                status_code=422,
            )

        campaign = await self.repository.get_campaign_by_code(code)
        if campaign is None:
            raise AntExException(
                "Marketing campaign not found",
                code="MARKETING_CAMPAIGN_NOT_FOUND",
                status_code=404,
            )
        if campaign.status != "active":
            raise AntExException(
                "Marketing campaign is inactive",
                code="MARKETING_CAMPAIGN_INACTIVE",
                status_code=409,
            )

        existing = await self.repository.get_attribution_by_user(user_id)
        if existing is not None:
            return existing

        attribution = MarketingAttribution(user_id=user_id, campaign_id=campaign.id)
        try:
            async with self.session.begin_nested():
                self.session.add(attribution)
                await self.session.flush()
        except IntegrityError:
            existing = await self.repository.get_attribution_by_user(user_id)
            if existing is None:
                raise
            return existing

        await self.session.refresh(attribution)
        return attribution
