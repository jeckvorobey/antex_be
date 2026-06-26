"""Роутер реферальной системы."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbDep
from app.core.config import settings
from app.schemas.aex import ReferralBindRequest, ReferralCodeOut, ReferralStatsOut
from app.services.referral import ReferralService, build_referral_link

router = APIRouter(prefix="/api/referral", tags=["referral"])

referral_service = ReferralService()


@router.get("/code", response_model=ReferralCodeOut)
async def get_referral_code(db: DbDep, user: CurrentUser) -> ReferralCodeOut:
    """Получить свой реферальный код."""
    code = await referral_service.get_or_create_referral_code(db, user)
    await db.commit()
    return ReferralCodeOut(
        referral_code=code,
        referral_link=build_referral_link(code, settings.telegram_bot_username),
    )


@router.get("/stats", response_model=ReferralStatsOut)
async def get_referral_stats(db: DbDep, user: CurrentUser) -> ReferralStatsOut:
    """Получить статистику рефералов."""
    count, earned = await referral_service.get_referral_stats(db, user)
    return ReferralStatsOut(
        total_referrals=count,
        total_earned=str(earned),
    )


@router.post("/bind")
async def bind_referral(
    body: ReferralBindRequest,
    db: DbDep,
    user: CurrentUser,
) -> dict[str, bool]:
    """Привязать реферала по коду (вызывается при deep-link)."""
    try:
        await referral_service.bind_referral(db, user, body.referral_code)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code in {"ALREADY_REFERRED", "INVALID_REFERRAL_CODE", "SELF_REFERRAL"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        raise
    await db.commit()
    return {"ok": True}
