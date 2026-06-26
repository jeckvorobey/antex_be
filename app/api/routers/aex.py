"""Роутер AEX (внутренняя валюта)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, CurrentUser, DbDep
from app.repositories.aex import (
    AexLedgerEntryRepository,
    AexPartnerRateRepository,
    AexPersonalRateRepository,
    AexRateRepository,
    AexWalletRepository,
)
from app.schemas.aex import (
    AexAdminCreditRequest,
    AexAdminDebitRequest,
    AexAdminRateCreate,
    AexAdminRateOut,
    AexAdminRateRowOut,
    AexAdminRateUpdate,
    AexOperationsResponse,
    AexRateOut,
    AexRateUpdate,
    AexTransferRequest,
    AexWalletOut,
    PaginatedAexOperationsResponse,
    PaginatedAexRateRowsResponse,
    PaginatedAexWalletsResponse,
    build_admin_operation_out,
    build_admin_rate_out,
    build_admin_rate_row_out,
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
    cursor: int | None = Query(default=None, ge=1),
) -> AexOperationsResponse:
    """Получить историю операций AEX (cursor-based pagination)."""
    entries, next_cursor = await aex_service.get_operations_cursor(
        db, user.id, limit=limit, cursor=cursor
    )
    return AexOperationsResponse(
        items=[build_aex_ledger_entry_out(e) for e in entries],
        next_cursor=next_cursor,
        limit=limit,
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
    global_rate = await rate_service.get_global_rate(db)
    personal_rates, _ = await AexPersonalRateRepository(db).get_all_with_users()
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


@admin_router.get("/rate", response_model=AexAdminRateOut)
async def get_admin_rate(db: DbDep, _: AdminUser) -> AexAdminRateOut:
    """Получить глобальную ставку AEX для админки."""
    rate = await rate_service.get_global_rate(db)
    return build_admin_rate_out(rate)


@admin_router.put("/rate", response_model=AexAdminRateOut)
async def update_admin_rate(
    body: AexAdminRateUpdate,
    db: DbDep,
    _: AdminUser,
) -> AexAdminRateOut:
    """Обновить глобальную ставку AEX для админки."""
    rate = await rate_service.update_global_rate(db, body.rate)
    await db.commit()
    return build_admin_rate_out(rate)


@admin_router.get("/rates/personal", response_model=PaginatedAexRateRowsResponse)
async def list_personal_rates(
    db: DbDep,
    _: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedAexRateRowsResponse:
    """Список персональных ставок AEX."""
    rates, total = await AexPersonalRateRepository(db).get_all_with_users(
        limit=limit,
        offset=offset,
    )
    return PaginatedAexRateRowsResponse(
        items=[build_admin_rate_row_out(rate) for rate in rates],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.post("/rates/personal", response_model=AexAdminRateRowOut)
async def create_personal_rate(
    body: AexAdminRateCreate,
    db: DbDep,
    _: AdminUser,
) -> AexAdminRateRowOut:
    """Создать персональную ставку AEX."""
    rate = await rate_service.set_personal_rate(db, body.userId, body.rate)
    await db.commit()
    return build_admin_rate_row_out(rate)


@admin_router.patch("/rates/personal/{rate_id}", response_model=AexAdminRateRowOut)
async def update_personal_rate(
    rate_id: int,
    body: AexAdminRateUpdate,
    db: DbDep,
    _: AdminUser,
) -> AexAdminRateRowOut:
    """Обновить персональную ставку AEX."""
    repo = AexPersonalRateRepository(db)
    rate = await repo.get_by_id(rate_id)
    if rate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    updated = await repo.update(rate, rate=body.rate)
    await db.commit()
    return build_admin_rate_row_out(updated)


@admin_router.delete("/rates/personal/{rate_id}")
async def delete_personal_rate(
    rate_id: int,
    db: DbDep,
    _: AdminUser,
) -> dict[str, bool]:
    """Удалить персональную ставку AEX."""
    repo = AexPersonalRateRepository(db)
    rate = await repo.get_by_id(rate_id)
    if rate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    await repo.delete(rate)
    await db.commit()
    return {"ok": True}


@admin_router.get("/rates/partner", response_model=PaginatedAexRateRowsResponse)
async def list_partner_rates(
    db: DbDep,
    _: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedAexRateRowsResponse:
    """Список партнёрских ставок AEX."""
    rates, total = await AexPartnerRateRepository(db).get_all_with_users(limit=limit, offset=offset)
    return PaginatedAexRateRowsResponse(
        items=[build_admin_rate_row_out(rate) for rate in rates],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.post("/rates/partner", response_model=AexAdminRateRowOut)
async def create_partner_rate(
    body: AexAdminRateCreate,
    db: DbDep,
    _: AdminUser,
) -> AexAdminRateRowOut:
    """Создать партнёрскую ставку AEX."""
    rate = await rate_service.set_partner_rate(db, body.userId, body.rate)
    await db.commit()
    return build_admin_rate_row_out(rate)


@admin_router.patch("/rates/partner/{rate_id}", response_model=AexAdminRateRowOut)
async def update_partner_rate(
    rate_id: int,
    body: AexAdminRateUpdate,
    db: DbDep,
    _: AdminUser,
) -> AexAdminRateRowOut:
    """Обновить партнёрскую ставку AEX."""
    repo = AexPartnerRateRepository(db)
    rate = await repo.get_by_id(rate_id)
    if rate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    updated = await repo.update(rate, rate=body.rate)
    await db.commit()
    return build_admin_rate_row_out(updated)


@admin_router.delete("/rates/partner/{rate_id}")
async def delete_partner_rate(
    rate_id: int,
    db: DbDep,
    _: AdminUser,
) -> dict[str, bool]:
    """Удалить партнёрскую ставку AEX."""
    repo = AexPartnerRateRepository(db)
    rate = await repo.get_by_id(rate_id)
    if rate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    await repo.delete(rate)
    await db.commit()
    return {"ok": True}


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


@admin_router.get("/wallets", response_model=PaginatedAexWalletsResponse)
async def list_wallets(
    db: DbDep,
    _: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
) -> PaginatedAexWalletsResponse:
    """Список всех AEX-кошельков."""
    wallets, total = await AexWalletRepository(db).get_all_with_users(
        limit=limit,
        offset=offset,
        search=search,
    )
    return PaginatedAexWalletsResponse(
        items=[build_admin_wallet_out(w) for w in wallets],
        total=total,
        limit=limit,
        offset=offset,
    )


@admin_router.get("/operations", response_model=PaginatedAexOperationsResponse)
async def list_all_operations(
    db: DbDep,
    _: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: int | None = Query(default=None, alias="userId", ge=1),
    entry_type: str | None = Query(default=None, alias="type"),
    date_from: str | None = Query(default=None, alias="dateFrom"),
    date_to: str | None = Query(default=None, alias="dateTo"),
) -> PaginatedAexOperationsResponse:
    """Журнал всех операций AEX."""
    repo = AexLedgerEntryRepository(db)
    parsed_date_from = (
        None
        if not date_from
        else datetime.fromisoformat(f"{date_from}T00:00:00+00:00")
    )
    parsed_date_to = None if not date_to else datetime.fromisoformat(f"{date_to}T23:59:59+00:00")
    entries = await repo.get_all_paginated(
        limit=limit,
        offset=offset,
        user_id=user_id,
        entry_type=entry_type,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
    )
    total = await repo.count_all(
        user_id=user_id,
        entry_type=entry_type,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
    )

    return PaginatedAexOperationsResponse(
        items=[build_admin_operation_out(e) for e in entries],
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
