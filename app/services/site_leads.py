"""Site lead application service."""

from __future__ import annotations

import hashlib
import json
import logging

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.site_lead import SiteLeadRepository
from app.repositories.user import UserRepository
from app.schemas.site_lead import SiteLeadCreate
from app.services.site_lead_notifications import notify_site_lead_created

logger = logging.getLogger(__name__)


async def create_site_lead(
    db: AsyncSession,
    payload: SiteLeadCreate,
    request: Request | None = None,
) -> object:
    await _guard_site_lead_submission(payload, _client_identity(request))
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


def _client_identity(request: Request | None) -> str:
    if request is None or request.client is None:
        return "unknown"
    return request.client.host


async def _guard_site_lead_submission(payload: SiteLeadCreate, client_ip: str) -> None:
    from app.core import redis as redis_module

    redis = redis_module.redis_client
    rate_key = f"site-lead:rate:{client_ip}"
    fingerprint = hashlib.sha256(
        json.dumps(payload.model_dump(), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    duplicate_key = f"site-lead:duplicate:{fingerprint}"

    try:
        count = await redis.incr(rate_key)
        if count == 1:
            await redis.expire(rate_key, 60)
        if count > 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много заявок",
            )
        if not await redis.set(duplicate_key, "1", ex=86_400, nx=True):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Заявка уже получена")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Site lead abuse guard unavailable")
        if settings.app_env != "production":
            logger.warning("Site lead abuse guard bypassed outside production")
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис заявок временно недоступен",
        ) from exc
