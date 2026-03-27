"""Роутер банков."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.repositories.bank import BankRepository
from app.schemas.bank import BankOut

router = APIRouter(prefix="/api/banks", tags=["banks"])


@router.get("", response_model=list[BankOut])
async def get_banks(db: DbDep) -> list[BankOut]:
    repo = BankRepository(db)
    banks = await repo.get_all()
    return [BankOut.model_validate(b) for b in banks]
