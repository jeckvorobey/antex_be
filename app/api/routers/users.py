"""Роутер пользователей."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.models.attribution import UserAcquisition
from app.schemas.user import UserOut, build_user_out

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser, db: DbDep) -> UserOut:
    referred_by: int | None = None
    acquisition = await db.scalar(
        select(UserAcquisition.referrer_user_id).where(
            UserAcquisition.user_id == user.id,
            UserAcquisition.source_type == "referral",
        )
    )
    if acquisition is not None:
        referred_by = acquisition
    return build_user_out(user, referred_by=referred_by)
