"""Публичные роуты (без аутентификации)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.repositories.allowance import AllowanceRepository
from app.services.rate import get_exchange_rates

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/rates")
async def public_rates(db: DbDep) -> dict:
    allowance_repo = AllowanceRepository(db)
    allowance = await allowance_repo.get_value()
    return await get_exchange_rates(allowance)
