"""Роутер AEX (внутренняя валюта)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, CurrentUser, DbDep
from app.repositories.aex import (
    AexLedgerEntryRepository,
    AexRateRepository,
    AexWalletRepository,
)
from app.schemas.aex import (
    AexAdminCreditRequest,
    AexAdminDebitRequest,
    AexAdminWalletOut,
    AexOperationsResponse,
    AexRateOut,
    AexRateUpdate,
    AexTransferRequest,
    AexWalletOut,
    build_admin_wallet_out,
    build_aex_ledger_entry_out,
    build_aex_rate_out,
    build_aex_wallet_out,
)
from app.services.aex import AexService
from app.services.aex_rate import AexRateService

router = APIRouter(prefix="/api/aex", tags=["aex"])
admin_router = APIRouter(prefix="/api/admin/aex", tags=["admin-aex"])

aex_service = AexService()
rate_service = AexRateService()


# ─── User API ────────────────────────────────────────────────────────────────


@router.get("/wallet", response_model=AexWalletOut)
async def get_wallet(db: DbDep, user: CurrentUser) -> AexWalletOut:
    """Получить баланс AEX текущего пользователя."""
    wallet = await aex_service.get_or_create_wallet(db, user.id)
    return build_aex_wallet_out(wallet)


@router.get("/operations", response_model=AexOperationsResponse)
async def get_operations(
    db: DbDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AexOperationsResponse:
    """Получить историю операций AEX."""
    entries, total = await aex_service.get_operations(db, user.id, limit=limit, offset=offset)
    return AexOperationsResponse(
        items=[build_aex_ledger_entry_out(e) for e in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/transfer")
async def transfer_aex(
    body: AexTransferRequest,
    db: DbDep,
    user: CurrentUser,
) -> dict[str, object]:
    """Продажа AEX (AEX -> X). Hold + создание заявки на обмен."""
    entry = await aex_service.hold(
        db,
        user.id,
        body.amount,
        reference_type="transfer",
        description="AEX transfer hold",
    )
    await db.commit()
    return {"ok": True, "entry_id": entry.id, "amount": str(body.amount)}


# ─── Admin API ───────────────────────────────────────────────────────────────


@admin_router.get("/rates", response_model=list[AexRateOut])
async def list_rates(db: DbDep, _: AdminUser) -> list[AexRateOut]:
    """Список ставок AEX (глобальная + персональные)."""
    from app.repositories.aex import AexPersonalRateRepository

    global_rate = await rate_service.get_global_rate(db)
    personal_rates = await AexPersonalRateRepository(db).get_all_with_users()
    result = [build_aex_rate_out(global_rate)]
    for pr in personal_rates:
        result.append(
            AexRateOut(
                id=pr.id,
                global_rate=pr.rate,
                createdAt=pr.createdAt,
                updatedAt=pr.updatedAt,
            )
        )
    return result


@admin_router.put("/rates/{rate_id}", response_model=AexRateOut)
async def update_rate(
    rate_id: int,
    body: AexRateUpdate,
    db: DbDep,
    _: AdminUser,
) -> AexRateOut:
    """Обновить глобальную ставку AEX."""
    repo = AexRateRepository(db)
    rate = await repo.get_by_id(rate_id)
    if not rate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    updated = await repo.update(rate, global_rate=body.global_rate)
    await db.commit()
    return build_aex_rate_out(updated)


@admin_router.get("/wallets", response_model=list[AexAdminWalletOut])
async def list_wallets(db: DbDep, _: AdminUser) -> list[AexAdminWalletOut]:
    """Список всех AEX-кошельков."""
    wallets = await AexWalletRepository(db).get_all_with_users()
    return [build_admin_wallet_out(w) for w in wallets]


@admin_router.get("/operations", response_model=AexOperationsResponse)
async def list_all_operations(
    db: DbDep,
    _: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AexOperationsResponse:
    """Журнал всех операций AEX."""
    repo = AexLedgerEntryRepository(db)
    entries = await repo.get_all_paginated(limit=limit, offset=offset)
    # Count total
    from sqlalchemy import func, select

    from app.models.aex import AexLedgerEntry

    count_result = await db.execute(select(func.count(AexLedgerEntry.id)))
    total = count_result.scalar_one()

    return AexOperationsResponse(
        items=[build_aex_ledger_entry_out(e) for e in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.post("/credit")
async def admin_credit(
    body: AexAdminCreditRequest,
    db: DbDep,
    _: AdminUser,
) -> dict[str, object]:
    """Ручное начисление AEX."""
    entry = await aex_service.credit(
        db,
        body.user_id,
        body.amount,
        reference_type="admin_credit",
        description=body.description or "Admin credit",
    )
    await db.commit()
    return {"ok": True, "entry_id": entry.id}


@admin_router.post("/debit")
async def admin_debit(
    body: AexAdminDebitRequest,
    db: DbDep,
    _: AdminUser,
) -> dict[str, object]:
    """Ручное списание AEX."""
    try:
        entry = await aex_service.debit(
            db,
            body.user_id,
            body.amount,
            reference_type="admin_debit",
            description=body.description or "Admin debit",
        )
    except Exception as exc:
        if getattr(exc, "code", None) == "INSUFFICIENT_FUNDS":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Insufficient AEX balance",
            ) from exc
        raise
    await db.commit()
    return {"ok": True, "entry_id": entry.id}


@admin_router.post("/generate-referral-codes")
async def generate_referral_codes(
    db: DbDep,
    _: AdminUser,
) -> dict[str, object]:
    """Batch-генерация реферальных кодов для пользователей без кода."""
    from app.services.referral import ReferralService

    service = ReferralService()
    generated = await service.generate_batch_referral_codes(db)
    await db.commit()
    return {"ok": True, "generated": generated}
