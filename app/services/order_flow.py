# ruff: noqa: RUF002
"""Сервис создания заявки с серверной калькуляцией."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.order import OrderStatus
from app.exceptions import AntExException
from app.repositories.city import CityRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.services.miniapp import calculate_miniapp_quote
from app.services.notifications import notify_order_created

logger = logging.getLogger(__name__)


async def create_order_for_user(
    db: AsyncSession,
    user,
    payload: MiniappOrderCreate,
) -> object:
    """Создаёт заявку, рассчитывая курс и сумму получения на сервере."""
    city_repo = CityRepository(db)
    user_repo = UserRepository(db)
    order_repo = OrderRepository(db)

    open_order = await order_repo.check_open(user.id)
    if open_order:
        raise AntExException(
            "User already has an active order",
            code="ORDER_ALREADY_EXISTS",
            status_code=409,
        )

    city_id = await _resolve_city_id(db, user, payload)
    city = await city_repo.get_by_id(city_id)
    if not city:
        raise AntExException("City not found", code="CITY_NOT_FOUND", status_code=404)

    manager = await user_repo.get_manager_by_city(city_id)
    if not manager:
        raise AntExException(
            "City manager is not configured",
            code="CITY_MANAGER_NOT_CONFIGURED",
            status_code=409,
        )

    quote = await calculate_miniapp_quote(
        db,
        payload.currency_sell,
        payload.currency_buy,
        payload.amount_sell,
    )
    order = await order_repo.create(
        UserId=user.id,
        CityId=city_id,
        currencySell=quote.currencySell,
        amountSell=quote.amountSell,
        currencyBuy=quote.currencyBuy,
        amountBuy=quote.amountBuy,
        rate=quote.rate,
        status=int(OrderStatus.NEW),
        address=payload.address,
        contactTelegram=payload.contact_telegram,
        methodGet=payload.method_get,
    )
    await db.commit()
    hydrated = await order_repo.get_one(order.id)

    try:
        await notify_order_created(hydrated, user, manager)
    except Exception:
        logger.exception("Failed to send order created notifications for order %s", order.id)

    return hydrated


async def _resolve_city_id(
    db: AsyncSession,
    user,
    payload: MiniappOrderCreate,
) -> int:
    """Выбирает город заявки: payload -> профиль пользователя -> первый город."""
    if payload.city_id:
        return payload.city_id
    if user.city_id:
        return user.city_id

    cities = await CityRepository(db).get_all()
    if not cities:
        raise AntExException("City not found", code="CITY_NOT_FOUND", status_code=404)
    return cities[0].id
