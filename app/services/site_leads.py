"""Site lead application service."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.site_lead import SiteLeadRepository
from app.repositories.user import UserRepository
from app.schemas.site_lead import SiteLeadCreate
from app.services.site_lead_notifications import notify_site_lead_created

logger = logging.getLogger(__name__)


async def create_site_lead(db: AsyncSession, payload: SiteLeadCreate) -> object:
    manager = await UserRepository(db).get_manager()
    repo = SiteLeadRepository(db)
    lead = await repo.create(**payload.model_dump())
    await db.commit()

    try:
        await notify_site_lead_created(lead, manager)
    except Exception:
        logger.exception("Failed to send site lead notification for lead %s", lead.id)

    return lead
