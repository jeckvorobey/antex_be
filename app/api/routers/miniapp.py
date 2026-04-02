"""Miniapp API на новой схеме."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep, MiniappUser
from app.schemas.miniapp import (
    MiniappCitiesResponse,
    MiniappOrderCreate,
    MiniappOrderCreatedResponse,
    MiniappOrdersResponse,
    MiniappProfileResponse,
    MiniappRatesResponse,
    build_miniapp_profile,
)
from app.services.miniapp import (
    list_miniapp_cities,
    list_miniapp_orders,
    list_miniapp_rates,
)
from app.services.order_flow import create_order_for_user

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])


@router.get("/cities", response_model=MiniappCitiesResponse)
async def get_cities(db: DbDep, _: MiniappUser) -> MiniappCitiesResponse:
    return await list_miniapp_cities(db)


@router.get("/rates", response_model=MiniappRatesResponse)
async def get_rates(db: DbDep, _: MiniappUser) -> MiniappRatesResponse:
    return await list_miniapp_rates(db)


@router.get("/orders", response_model=MiniappOrdersResponse)
async def get_orders(db: DbDep, user: MiniappUser) -> MiniappOrdersResponse:
    return await list_miniapp_orders(db, user.id)


@router.post("/orders", response_model=MiniappOrderCreatedResponse)
async def create_order(
    body: MiniappOrderCreate,
    db: DbDep,
    user: MiniappUser,
) -> MiniappOrderCreatedResponse:
    order = await create_order_for_user(db, user, body)
    return MiniappOrderCreatedResponse(orderId=order.id)


@router.get("/profile", response_model=MiniappProfileResponse)
async def get_profile(user: MiniappUser) -> MiniappProfileResponse:
    return build_miniapp_profile(user)
