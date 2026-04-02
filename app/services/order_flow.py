"""Сервис создания заявки без калькуляции."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.order import OrderStatus
from app.exceptions import AntExException
from app.repositories.city import CityRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.services.notifications import notify_order_created

logger = logging.getLogger(__name__)


async def create_order_for_user(
    db: AsyncSession,
    user,
    payload: MiniappOrderCreate,
) -> object:
    city_repo = CityRepository(db)
    user_repo = UserRepository(db)
    order_repo = OrderRepository(db)

    city = await city_repo.get_by_id(payload.city_id)
    if not city:
        raise AntExException("City not found", code="CITY_NOT_FOUND", status_code=404)

    manager = await user_repo.get_manager_by_city(payload.city_id)
    if not manager:
        raise AntExException(
            "City manager is not configured",
            code="CITY_MANAGER_NOT_CONFIGURED",
            status_code=409,
        )

    order = await order_repo.create(
        UserId=user.id,
        CityId=payload.city_id,
        currencySell=payload.currency_sell.upper(),
        amountSell=payload.amount_sell,
        currencyBuy=payload.currency_buy.upper(),
        amountBuy=payload.amount_buy,
        rate=payload.rate,
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
