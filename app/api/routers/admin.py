"""Роутер административной панели."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbDep
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.user import UserRole
from app.models.order import Order
from app.models.user import User
from app.repositories.admin import AdminRepository
from app.repositories.city import CityRepository
from app.repositories.config import ConfigRepository
from app.repositories.order import OrderRepository
from app.repositories.rate import RateRepository
from app.repositories.site_lead import SiteLeadRepository
from app.repositories.user import UserRepository
from app.schemas.admin import (
    AdminCreate,
    AdminLogin,
    AdminOut,
    AdminPasswordUpdate,
    AdminSummaryOut,
    AdminSummaryRateOut,
    AdminTokenResponse,
)
from app.schemas.city import CityCreate, CityOut, CityUpdate, build_city_out
from app.schemas.config import AppConfigOut, AppConfigUpdate
from app.schemas.order import OrderOut, OrderStatusUpdate, build_order_out
from app.schemas.rate import AdminRateOut, RateCreate, RateUpdate, build_admin_rate_out
from app.schemas.site_lead import SiteLeadOut, build_site_lead_out
from app.schemas.user import UserOut, UserUpdate, build_user_out
from app.services.exchange import ExchangeService
from app.services.order_status import update_order_status as apply_order_status

router = APIRouter(prefix="/api/admin", tags=["admin"])


def build_password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_today_start_for_timezone(
    timezone_name: str,
    *,
    now: datetime | None = None,
) -> datetime:
    """Возвращает UTC-момент локальной полуночи для заданной timezone."""
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone = UTC

    current_time = now or datetime.now(UTC)
    local_today = current_time.astimezone(timezone).date()
    local_start = datetime.combine(local_today, time.min, tzinfo=timezone)
    return local_start.astimezone(UTC)


@router.post("/login", response_model=AdminTokenResponse)
async def admin_login(body: AdminLogin, db: DbDep) -> AdminTokenResponse:
    repo = AdminRepository(db)
    admin = await repo.get_by_username(body.username)
    password_hash = build_password_hash(body.password)
    if not admin or admin.password_hash != password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

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
async def admin_refresh(_: DbDep, admin: AdminUser) -> AdminTokenResponse:
    access = create_access_token(
        {"sub": str(admin.id), "type": "admin"},
        ttl=settings.admin_access_ttl_seconds,
    )
    refresh = create_access_token(
        {"sub": str(admin.id), "type": "admin_refresh"},
        ttl=settings.admin_refresh_ttl_seconds,
    )
    return AdminTokenResponse(access_token=access, refresh_token=refresh)


@router.post("/logout")
async def admin_logout(_: AdminUser) -> dict[str, bool]:
    return {"ok": True}


@router.get("/list", response_model=list[AdminOut])
async def list_admins(db: DbDep, _: AdminUser) -> list[AdminOut]:
    return [AdminOut.model_validate(admin) for admin in await AdminRepository(db).get_all()]


@router.post("/add", response_model=AdminOut, status_code=status.HTTP_201_CREATED)
async def create_admin(body: AdminCreate, db: DbDep, _: AdminUser) -> AdminOut:
    repo = AdminRepository(db)
    if await repo.get_by_username(body.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    if await repo.get_by_email(body.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    admin = await repo.create(
        username=body.username,
        email=body.email,
        password_hash=build_password_hash(body.password),
    )
    await db.commit()
    return AdminOut.model_validate(admin)


@router.put("/password")
async def update_admin_password(
    body: AdminPasswordUpdate,
    db: DbDep,
    _: AdminUser,
) -> dict[str, bool]:
    repo = AdminRepository(db)
    admin = await repo.get_by_id(body.admin_id)
    if not admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    await repo.update(admin, password_hash=build_password_hash(body.password))
    await db.commit()
    return {"ok": True}


@router.delete("/delete/{admin_id}")
async def delete_admin(admin_id: int, db: DbDep, current_admin: AdminUser) -> dict[str, bool]:
    repo = AdminRepository(db)
    admin = await repo.get_by_id(admin_id)
    if not admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")
    if current_admin.id == admin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete yourself",
        )

    await repo.delete(admin)
    await db.commit()
    return {"ok": True}


@router.get("/summary", response_model=AdminSummaryOut)
async def get_admin_summary(db: DbDep, _: AdminUser) -> AdminSummaryOut:
    """Возвращает MVP-метрики для дашборда админки."""
    today_start = get_today_start_for_timezone(settings.timezone)
    orders_today_result = await db.execute(
        select(func.count(Order.id)).where(
            Order.createdAt >= today_start,
            Order.destroyTime.is_(None),
        )
    )
    users_total_result = await db.execute(select(func.count(User.id)))
    featured_rates = await ExchangeService().get_featured_pair_snapshots(db)

    return AdminSummaryOut(
        orders_today=orders_today_result.scalar_one(),
        users_total=users_total_result.scalar_one(),
        featured_rates=[
            AdminSummaryRateOut(
                pairId=pair.pair_id,
                label=pair.label,
                finalRate=pair.client_rate,
                finalRateDisplay=pair.rate_display,
            )
            for pair in featured_rates[:3]
        ],
    )


@router.get("/cities", response_model=list[CityOut])
async def list_cities(db: DbDep, _: AdminUser) -> list[CityOut]:
    repo = CityRepository(db)
    return [build_city_out(city) for city in await repo.get_all()]


@router.get("/cities/{city_id}", response_model=CityOut)
async def get_city(city_id: int, db: DbDep, _: AdminUser) -> CityOut:
    city = await CityRepository(db).get_by_id(city_id)
    if not city:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    return build_city_out(city)


@router.post("/cities", response_model=CityOut, status_code=status.HTTP_201_CREATED)
async def create_city(body: CityCreate, db: DbDep, _: AdminUser) -> CityOut:
    repo = CityRepository(db)
    city = await repo.create(**body.model_dump())
    await db.commit()
    return build_city_out(city)


@router.patch("/cities/{city_id}", response_model=CityOut)
async def update_city(city_id: int, body: CityUpdate, db: DbDep, _: AdminUser) -> CityOut:
    repo = CityRepository(db)
    city = await repo.get_by_id(city_id)
    if not city:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    updated = await repo.update(city, **body.model_dump(exclude_none=True))
    await db.commit()
    return build_city_out(updated)


@router.delete("/cities/{city_id}")
async def delete_city(city_id: int, db: DbDep, _: AdminUser) -> dict[str, bool]:
    repo = CityRepository(db)
    city = await repo.get_by_id(city_id)
    if not city:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")
    await repo.delete(city)
    await db.commit()
    return {"ok": True}


@router.get("/users", response_model=list[UserOut])
async def list_users(db: DbDep, _: AdminUser) -> list[UserOut]:
    repo = UserRepository(db)
    return [build_user_out(user) for user in await repo.list_all()]


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: DbDep, _: AdminUser) -> UserOut:
    repo = UserRepository(db)
    user = await repo.get_one(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return build_user_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, body: UserUpdate, db: DbDep, _: AdminUser) -> UserOut:
    repo = UserRepository(db)
    user = await repo.get_one(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)
    new_role = update_data.get("role", user.role)
    new_city_id = update_data.get("city_id", user.city_id)

    if new_city_id is not None:
        city = await CityRepository(db).get_by_id(new_city_id)
        if not city:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="City not found")

    if new_role == UserRole.MANAGER:
        current_manager = await repo.get_manager()
        if current_manager and current_manager.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Manager is already assigned",
            )

    updated = await repo.update(user, **update_data)
    await db.commit()
    updated = await repo.get_one(updated.id)
    return build_user_out(updated)


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(
    db: DbDep,
    _: AdminUser,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[OrderOut]:
    repo = OrderRepository(db)
    if date_from and date_to:
        orders = await repo.list_for_admin(date_from=date_from, date_to=date_to)
    else:
        orders = await repo.list_for_admin()
    return [build_order_out(order) for order in orders]


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, db: DbDep, _: AdminUser) -> OrderOut:
    order = await OrderRepository(db).get_one(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return build_order_out(order)


@router.patch("/orders/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    body: OrderStatusUpdate,
    db: DbDep,
    _: AdminUser,
) -> OrderOut:
    try:
        hydrated = await apply_order_status(db, order_id=order_id, status=body.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            ) from exc
        raise
    return build_order_out(hydrated)


@router.get("/site-leads", response_model=list[SiteLeadOut])
async def list_site_leads(db: DbDep, _: AdminUser) -> list[SiteLeadOut]:
    return [build_site_lead_out(lead) for lead in await SiteLeadRepository(db).list_all()]


@router.get("/rates", response_model=list[AdminRateOut])
async def list_rates(db: DbDep, _: AdminUser) -> list[AdminRateOut]:
    return [build_admin_rate_out(rate) for rate in await RateRepository(db).get_all()]


@router.get("/rates/{rate_id}", response_model=AdminRateOut)
async def get_rate(rate_id: int, db: DbDep, _: AdminUser) -> AdminRateOut:
    rate = await RateRepository(db).get_by_id(rate_id)
    if not rate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    return build_admin_rate_out(rate)


@router.post("/rates", response_model=AdminRateOut, status_code=status.HTTP_201_CREATED)
async def create_rate(body: RateCreate, db: DbDep, _: AdminUser) -> AdminRateOut:
    rate = await RateRepository(db).create(**body.model_dump())
    await db.commit()
    return build_admin_rate_out(rate)


@router.patch("/rates/{rate_id}", response_model=AdminRateOut)
async def update_rate(rate_id: int, body: RateUpdate, db: DbDep, _: AdminUser) -> AdminRateOut:
    repo = RateRepository(db)
    rate = await repo.get_by_id(rate_id)
    if not rate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    updated = await repo.update(rate, **body.model_dump(exclude_none=True))
    await db.commit()
    return build_admin_rate_out(updated)


@router.delete("/rates/{rate_id}")
async def delete_rate(rate_id: int, db: DbDep, _: AdminUser) -> dict[str, bool]:
    repo = RateRepository(db)
    rate = await repo.get_by_id(rate_id)
    if not rate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    await repo.delete(rate)
    await db.commit()
    return {"ok": True}


@router.get("/config", response_model=AppConfigOut)
async def get_config(db: DbDep, _: AdminUser) -> AppConfigOut:
    return AppConfigOut.model_validate(await ConfigRepository(db).get_or_create())


@router.patch("/config", response_model=AppConfigOut)
async def update_config(body: AppConfigUpdate, db: DbDep, _: AdminUser) -> AppConfigOut:
    repo = ConfigRepository(db)
    if body.enabled is not None:
        await repo.set_enabled(body.enabled)
    config = await repo.get_or_create()
    await db.commit()
    return AppConfigOut.model_validate(config)


@router.post("/rates/refresh")
async def refresh_rates(db: DbDep, _: AdminUser) -> dict[str, object]:
    from app.services.rate_fetcher import fetch_and_save_rates

    rates = await fetch_and_save_rates(db)
    return {"ok": True, "rates": rates}
