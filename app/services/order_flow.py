# ruff: noqa: RUF002
"""Сервис создания заявки с серверной калькуляцией."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.country import Country
from app.enums.order import MethodGet
from app.enums.order import OrderStatus
from app.exceptions import AntExException
from app.repositories.city import CityRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.services.auth import resolve_trusted_contact
from app.services.exchange import ExchangeQuoteInput, ExchangeService
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

    trusted_contact = resolve_trusted_contact(user)
    if not trusted_contact.ready:
        raise AntExException(
            "Trusted contact is not ready",
            code="TRUSTED_CONTACT_NOT_READY",
            status_code=409,
        )

    city = await _resolve_city(db, payload)
    _validate_country_and_method(payload, city)

    manager = None
    if city is not None:
        manager = await user_repo.get_manager_by_city(city.id)
        if not manager:
            raise AntExException(
                "City manager is not configured",
                code="CITY_MANAGER_NOT_CONFIGURED",
                status_code=409,
            )

    quote = await ExchangeService().get_quote(
        db,
        ExchangeQuoteInput(
            currency_sell=payload.currency_sell,
            currency_buy=payload.currency_buy,
            amount_sell=payload.amount_sell,
        ),
    )
    _validate_quote_country(payload.country, quote.currency_buy)

    order = await order_repo.create(
        UserId=user.id,
        CityId=city.id if city else None,
        country=payload.country,
        currencySell=quote.currency_sell,
        amountSell=quote.amount_sell,
        currencyBuy=quote.currency_buy,
        amountBuy=quote.amount_buy,
        rate=quote.rate,
        status=int(OrderStatus.CREATED),
        contactTelegram=trusted_contact.contact,
        methodGet=payload.method_get,
    )
    await db.commit()
    hydrated = await order_repo.get_one(order.id)

    try:
        await notify_order_created(hydrated, user, manager)
    except Exception:
        logger.exception("Failed to send order created notifications for order %s", order.id)

    return hydrated


async def _resolve_city(
    db: AsyncSession,
    payload: MiniappOrderCreate,
) -> object | None:
    """Возвращает город заявки только для cash-потока."""
    if payload.city_id is None:
        return None

    city = await CityRepository(db).get_by_id(payload.city_id)
    if not city:
        raise AntExException("City not found", code="CITY_NOT_FOUND", status_code=404)
    return city


def _validate_country_and_method(payload: MiniappOrderCreate, city) -> None:
    if payload.method_get == MethodGet.CASH:
        if payload.city_id is None:
            raise AntExException(
                "City is required for cash method",
                code="CITY_REQUIRED_FOR_CASH",
                status_code=422,
            )
        if city is None:
            raise AntExException("City not found", code="CITY_NOT_FOUND", status_code=404)
        if city.country != payload.country:
            raise AntExException(
                "City does not match country",
                code="CITY_COUNTRY_MISMATCH",
                status_code=422,
            )
        return

    if payload.method_get == MethodGet.QRCODE:
        return

    raise AntExException(
        "Unsupported receive method",
        code="UNSUPPORTED_METHOD",
        status_code=422,
    )


def _validate_quote_country(country: Country, currency_buy: str) -> None:
    expected_country = {
        "THB": Country.THAILAND,
        "GEL": Country.GEORGIA,
        "VND": Country.VIETNAM,
    }.get(currency_buy.upper())
    if expected_country is None or expected_country != country:
        raise AntExException(
            "Currency pair does not match country",
            code="COUNTRY_CURRENCY_MISMATCH",
            status_code=422,
        )
