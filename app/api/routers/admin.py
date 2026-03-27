"""Роутер административной панели."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.api.deps import AdminUser, DbDep
from app.core.config import settings
from app.core.security import create_access_token
from app.repositories.admin import AdminRepository
from app.repositories.allowance import AllowanceRepository
from app.repositories.bank import BankRepository
from app.repositories.card import CardRepository
from app.repositories.config import ConfigRepository
from app.repositories.limitation import LimitationRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.admin import AdminLogin, AdminOut, AdminTokenResponse
from app.schemas.allowance import AllowanceOut, AllowanceUpdate
from app.schemas.bank import BankOut
from app.schemas.card import CardCreate, CardOut
from app.schemas.config import AppConfigOut
from app.schemas.limitation import LimitationOut, LimitationUpdate
from app.schemas.order import OrderOut
from app.schemas.user import UserOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- Auth ---

@router.post("/login", response_model=AdminTokenResponse)
async def admin_login(body: AdminLogin, db: DbDep) -> AdminTokenResponse:
    repo = AdminRepository(db)
    admin = await repo.get_by_username(body.username)
    pw_hash = hashlib.sha256(body.password.encode()).hexdigest()
    if not admin or admin.password_hash != pw_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_access_token(
        {"sub": str(admin.id), "type": "admin"},
        ttl=settings.admin_access_ttl_seconds,
    )
    refresh = create_access_token(
        {"sub": str(admin.id), "type": "admin_refresh"},
        ttl=settings.admin_refresh_ttl_seconds,
    )
    return AdminTokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=AdminTokenResponse)
async def admin_refresh(db: DbDep, admin: AdminUser) -> AdminTokenResponse:
    access = create_access_token(
        {"sub": str(admin.id), "type": "admin"},  # type: ignore[attr-defined]
        ttl=settings.admin_access_ttl_seconds,
    )
    refresh = create_access_token(
        {"sub": str(admin.id), "type": "admin_refresh"},  # type: ignore[attr-defined]
        ttl=settings.admin_refresh_ttl_seconds,
    )
    return AdminTokenResponse(access_token=access, refresh_token=refresh)


@router.post("/logout")
async def admin_logout(admin: AdminUser) -> dict:
    return {"ok": True}


# --- Cards ---

@router.get("/cards", response_model=list[CardOut])
async def list_cards(db: DbDep, _: AdminUser) -> list[CardOut]:
    repo = CardRepository(db)
    return [CardOut.model_validate(c) for c in await repo.get_all()]


@router.post("/cards", response_model=CardOut)
async def create_card(body: CardCreate, db: DbDep, _: AdminUser) -> CardOut:
    repo = CardRepository(db)
    card = await repo.create(**body.model_dump())
    return CardOut.model_validate(card)


@router.patch("/cards/{card_id}/toggle", response_model=CardOut)
async def toggle_card(card_id: int, db: DbDep, _: AdminUser) -> CardOut:
    repo = CardRepository(db)
    card = await repo.toggle_active(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return CardOut.model_validate(card)


@router.delete("/cards/{card_id}")
async def delete_card(card_id: int, db: DbDep, _: AdminUser) -> dict:
    repo = CardRepository(db)
    card = await repo.get_by_id(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    await repo.delete(card)
    return {"ok": True}


# --- Banks ---

@router.get("/banks", response_model=list[BankOut])
async def list_banks(db: DbDep, _: AdminUser) -> list[BankOut]:
    repo = BankRepository(db)
    return [BankOut.model_validate(b) for b in await repo.get_all()]


# --- Rates ---

@router.post("/rates/refresh")
async def refresh_rates(db: DbDep, _: AdminUser) -> dict:
    from app.services.rate import fetch_from_coingecko, store_rates
    from app.repositories.rate import RateRepository
    rates = await fetch_from_coingecko()
    await store_rates(rates)
    repo = RateRepository(db)
    for currency, price in rates.items():
        await repo.upsert(currency, price)
    return rates


# --- Allowance ---

@router.get("/allowance", response_model=AllowanceOut)
async def get_allowance(db: DbDep, _: AdminUser) -> AllowanceOut:
    repo = AllowanceRepository(db)
    value = await repo.get_value()
    from app.models.allowance import Allowance
    from sqlalchemy import select
    result = await db.execute(select(Allowance).limit(1))
    obj = result.scalar_one_or_none()
    if not obj:
        obj = await repo.update_value(value)
    return AllowanceOut.model_validate(obj)


@router.put("/allowance", response_model=AllowanceOut)
async def update_allowance(body: AllowanceUpdate, db: DbDep, _: AdminUser) -> AllowanceOut:
    repo = AllowanceRepository(db)
    obj = await repo.update_value(body.value)
    return AllowanceOut.model_validate(obj)


# --- Limitations ---

@router.get("/limitations", response_model=list[LimitationOut])
async def list_limitations(db: DbDep, _: AdminUser) -> list[LimitationOut]:
    repo = LimitationRepository(db)
    return [LimitationOut.model_validate(l) for l in await repo.get_all_with_bank()]


@router.put("/limitations/{lim_id}", response_model=LimitationOut)
async def update_limitation(lim_id: int, body: LimitationUpdate, db: DbDep, _: AdminUser) -> LimitationOut:
    repo = LimitationRepository(db)
    lim = await repo.get_by_id(lim_id)
    if not lim:
        raise HTTPException(status_code=404, detail="Limitation not found")
    updated = await repo.update(lim, **{k: v for k, v in body.model_dump().items() if v is not None})
    return LimitationOut.model_validate(updated)


# --- Orders ---

@router.get("/orders", response_model=list[OrderOut])
async def list_orders(
    db: DbDep,
    _: AdminUser,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[OrderOut]:
    repo = OrderRepository(db)
    if date_from and date_to:
        orders = await repo.get_by_interval(date_from, date_to)
    else:
        orders = await repo.get_all()
    return [OrderOut.model_validate(o) for o in orders]


# --- Users ---

@router.get("/users", response_model=list[UserOut])
async def list_users(db: DbDep, _: AdminUser) -> list[UserOut]:
    repo = UserRepository(db)
    return [UserOut.model_validate(u) for u in await repo.get_all()]


# --- Config ---

@router.get("/config", response_model=AppConfigOut)
async def get_config(db: DbDep, _: AdminUser) -> AppConfigOut:
    repo = ConfigRepository(db)
    config = await repo.get_or_create()
    return AppConfigOut.model_validate(config)


@router.post("/config/toggle", response_model=AppConfigOut)
async def toggle_config(db: DbDep, _: AdminUser) -> AppConfigOut:
    repo = ConfigRepository(db)
    config = await repo.toggle_enabled()
    return AppConfigOut.model_validate(config)
