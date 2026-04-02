"""Роутер административной панели."""

from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminUser, DbDep
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.user import UserRole
from app.repositories.admin import AdminRepository
from app.repositories.city import CityRepository
from app.repositories.config import ConfigRepository
from app.repositories.order import OrderRepository
from app.repositories.rate import RateRepository
from app.repositories.user import UserRepository
from app.schemas.admin import AdminLogin, AdminTokenResponse
from app.schemas.city import CityCreate, CityOut, CityUpdate, build_city_out
from app.schemas.config import AppConfigOut, AppConfigUpdate
from app.schemas.order import OrderOut, OrderStatusUpdate, build_order_out
from app.schemas.rate import RateCreate, RateOut, RateUpdate
from app.schemas.user import UserOut, UserUpdate, build_user_out

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/login", response_model=AdminTokenResponse)
async def admin_login(body: AdminLogin, db: DbDep) -> AdminTokenResponse:
    repo = AdminRepository(db)
    admin = await repo.get_by_username(body.username)
    password_hash = hashlib.sha256(body.password.encode()).hexdigest()
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

    if new_role == UserRole.MANAGER and new_city_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manager must be assigned to a city",
        )

    if new_role == UserRole.MANAGER and new_city_id is not None:
        current_manager = await repo.get_manager_by_city(new_city_id)
        if current_manager and current_manager.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="City already has a manager",
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
        orders = await repo.get_by_interval(date_from, date_to)
    else:
        orders = await repo.list_all()
    hydrated = [await repo.get_one(order.id) for order in orders]
    return [build_order_out(order) for order in hydrated if order is not None]


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
    repo = OrderRepository(db)
    order = await repo.update_status(order_id, body.status)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    await db.commit()
    hydrated = await repo.get_one(order_id)
    return build_order_out(hydrated)


@router.get("/rates", response_model=list[RateOut])
async def list_rates(db: DbDep, _: AdminUser) -> list[RateOut]:
    return [RateOut.model_validate(rate) for rate in await RateRepository(db).get_all()]


@router.get("/rates/{rate_id}", response_model=RateOut)
async def get_rate(rate_id: int, db: DbDep, _: AdminUser) -> RateOut:
    rate = await RateRepository(db).get_by_id(rate_id)
    if not rate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    return RateOut.model_validate(rate)


@router.post("/rates", response_model=RateOut, status_code=status.HTTP_201_CREATED)
async def create_rate(body: RateCreate, db: DbDep, _: AdminUser) -> RateOut:
    rate = await RateRepository(db).create(**body.model_dump())
    await db.commit()
    return RateOut.model_validate(rate)


@router.patch("/rates/{rate_id}", response_model=RateOut)
async def update_rate(rate_id: int, body: RateUpdate, db: DbDep, _: AdminUser) -> RateOut:
    repo = RateRepository(db)
    rate = await repo.get_by_id(rate_id)
    if not rate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    updated = await repo.update(rate, **body.model_dump(exclude_none=True))
    await db.commit()
    return RateOut.model_validate(updated)


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
    config = await ConfigRepository(db).set_enabled(body.enabled)
    await db.commit()
    return AppConfigOut.model_validate(config)
