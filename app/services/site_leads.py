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
    logger.info(
        "Site lead creation requested: messenger=%s topic_present=%s source=%s",
        payload.messenger,
        bool(payload.topic),
        payload.source,
    )
    manager = await UserRepository(db).get_manager()
    logger.info(
        "Site lead manager resolved: manager_user_id=%s manager_telegram_id=%s",
        getattr(manager, "id", None),
        getattr(manager, "telegram_id", None),
    )
    repo = SiteLeadRepository(db)
    lead = await repo.create(**payload.model_dump())
    await db.commit()
    logger.info("Site lead saved: lead_id=%s source=%s", lead.id, lead.source)

    try:
        logger.info(
            "Site lead notification attempt: lead_id=%s manager_user_id=%s manager_telegram_id=%s",
            lead.id,
            getattr(manager, "id", None),
            getattr(manager, "telegram_id", None),
        )
        await notify_site_lead_created(lead, manager)
        logger.info("Site lead notification completed: lead_id=%s", lead.id)
    except Exception:
        logger.exception(
            "Failed to send site lead notification: lead_id=%s manager_user_id=%s "
            "manager_telegram_id=%s",
            lead.id,
            getattr(manager, "id", None),
            getattr(manager, "telegram_id", None),
        )

    return lead
