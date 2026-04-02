"""Сервисы miniapp API."""

from __future__ import annotations

from app.repositories.city import CityRepository
from app.repositories.order import OrderRepository
from app.repositories.rate import RateRepository
from app.schemas.city import build_city_out
from app.schemas.miniapp import (
    MiniappCitiesResponse,
    MiniappOrdersResponse,
    MiniappRatesResponse,
    build_miniapp_order_item,
)
from app.schemas.rate import RateOut


async def list_miniapp_cities(db) -> MiniappCitiesResponse:
    cities = await CityRepository(db).get_all()
    return MiniappCitiesResponse(items=[build_city_out(city) for city in cities])


async def list_miniapp_rates(db) -> MiniappRatesResponse:
    rates = await RateRepository(db).get_all()
    return MiniappRatesResponse(items=[RateOut.model_validate(rate) for rate in rates])


async def list_miniapp_orders(db, user_id: int) -> MiniappOrdersResponse:
    orders = await OrderRepository(db).get_user_orders(user_id, limit=100)
    return MiniappOrdersResponse(items=[build_miniapp_order_item(order) for order in orders])
