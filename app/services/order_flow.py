# ruff: noqa: RUF002
"""Сервис создания предварительной заявки."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.country import Country
from app.enums.order import MethodGet, OrderStatus
from app.exceptions import AntExException
from app.repositories.city import CityRepository
from app.repositories.config import ConfigRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.services.aex import AexService
from app.services.exchange import CANONICAL_BUY_CURRENCIES, ExchangeService
from app.services.notifications import notify_order_created
from app.services.order_numbers import OrderNumberService

logger = logging.getLogger(__name__)
MAX_ACTIVE_ORDERS_PER_USER = 10
TOKEN_CURRENCY = "ATXG"
TOKEN_RATE_BASE_CURRENCY = "USDT"

MIN_AMOUNT_BY_METHOD: dict[str, dict[str, int]] = {
    MethodGet.CASH: {"RUB": 25_000, "USDT": 500},
    MethodGet.QRCODE: {"RUB": 15_000, "USDT": 300},
    MethodGet.BANK_ACCOUNT: {"RUB": 5_000, "USDT": 100},
    MethodGet.PAY_SERVICES: {"RUB": 5_000, "USDT": 100},
}


async def create_order_for_user(
    db: AsyncSession,
    user,
    payload: MiniappOrderCreate,
) -> object:
    """Создаёт предварительную заявку с клиентским расчётом miniapp."""
    order_repo = OrderRepository(db)
    logger.info(
        "Order creation requested: user_id=%s telegram_id=%s country=%s method=%s "
        "currency_sell=%s currency_buy=%s amount_sell=%s amount_buy=%s rate=%s",
        getattr(user, "id", None),
        getattr(user, "telegram_id", None),
        payload.country,
        payload.method_get,
        payload.currency_sell.upper(),
        payload.currency_buy.upper(),
        payload.amount_sell,
        payload.amount_buy,
        payload.rate,
    )

    open_orders_count = await order_repo.count_open(user.id)
    if open_orders_count >= MAX_ACTIVE_ORDERS_PER_USER:
        raise AntExException(
            "User has reached active orders limit",
            code="ORDER_ALREADY_EXISTS",
            status_code=409,
        )

    city = await _resolve_city(db, payload)
    _validate_country_and_method(payload, city)
    _validate_min_amount(payload)
    await _validate_rate_pair_exists(db, payload)
    currency_sell = _normalize_token_currency(payload.currency_sell)
    currency_buy = payload.currency_buy.upper()
    _validate_quote_country(payload.country, currency_buy)
    await _validate_aex_withdrawal_balance(db, user.id, payload)

    manager = await UserRepository(db).get_manager()
    logger.info(
        "Order manager resolved: user_id=%s manager_user_id=%s manager_telegram_id=%s",
        getattr(user, "id", None),
        getattr(manager, "id", None),
        getattr(manager, "telegram_id", None),
    )

    try:
        order_created_at = datetime.now(UTC)
        order = await order_repo.create(
            UserId=user.id,
            CityId=city.id if city else None,
            country=payload.country,
            currencySell=currency_sell,
            amountSell=payload.amount_sell,
            currencyBuy=currency_buy,
            amountBuy=payload.amount_buy,
            rate=payload.rate,
            status=int(OrderStatus.CREATED),
            contactTelegram=user.username or None,
            methodGet=payload.method_get,
            publicNumber=await OrderNumberService(db).next_public_number(
                created_at=order_created_at
            ),
            createdAt=order_created_at,
            updatedAt=order_created_at,
        )
        config = await ConfigRepository(db).get_or_create()
        from app.services.attribution import AttributionService

        attribution = await AttributionService(db).resolve_order_attribution(
            user.id,
            order_created_at,
            config.marketing_attribution_window_days,
        )
        attribution.order_id = order.id
        db.add(attribution)
        if _is_aex_withdrawal(payload):
            await AexService().hold_order_withdrawal(
                db,
                user.id,
                Decimal(str(payload.amount_sell)),
                order_id=order.id,
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    hydrated = await order_repo.get_one(order.id)
    logger.info(
        "Order saved: order_id=%s public_number=%s user_id=%s status=%s",
        order.id,
        getattr(order, "publicNumber", None),
        getattr(user, "id", None),
        getattr(order, "status", None),
    )

    try:
        logger.info(
            "Order notification attempt: order_id=%s public_number=%s manager_user_id=%s "
            "manager_telegram_id=%s",
            order.id,
            getattr(order, "publicNumber", None),
            getattr(manager, "id", None),
            getattr(manager, "telegram_id", None),
        )
        await notify_order_created(hydrated, user, manager)
        logger.info(
            "Order notification completed: order_id=%s public_number=%s",
            order.id,
            getattr(order, "publicNumber", None),
        )
    except Exception:
        logger.exception(
            "Failed to send order created notifications: order_id=%s public_number=%s "
            "manager_user_id=%s manager_telegram_id=%s",
            order.id,
            getattr(order, "publicNumber", None),
            getattr(manager, "id", None),
            getattr(manager, "telegram_id", None),
        )

    return hydrated


async def _validate_rate_pair_exists(db: AsyncSession, payload: MiniappOrderCreate) -> None:
    exchange_service = ExchangeService()
    direct_key = _resolve_rate_pair_key(exchange_service, payload)
    if direct_key is None:
        raise AntExException(
            "Rate pair is unavailable",
            code="RATE_PAIR_UNAVAILABLE",
            status_code=422,
        )

    rates = await exchange_service.load_rates(db)
    if not any(rate.currency.upper() == direct_key for rate in rates):
        raise AntExException(
            "Rate pair is unavailable",
            code="RATE_PAIR_UNAVAILABLE",
            status_code=422,
        )


async def _resolve_city(
    db: AsyncSession,
    payload: MiniappOrderCreate,
) -> object | None:
    """Возвращает город заявки только для доставки наличных."""
    if payload.method_get != MethodGet.CASH or payload.city_id is None:
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

    if payload.method_get in {
        MethodGet.QRCODE,
        MethodGet.BANK_ACCOUNT,
        MethodGet.PAY_SERVICES,
    }:
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


def _validate_min_amount(payload: MiniappOrderCreate) -> None:
    currency_sell = payload.currency_sell.upper()
    method = payload.method_get
    min_amount = get_min_amount(method, currency_sell)
    if min_amount and payload.amount_sell < min_amount:
        raise AntExException(
            f"Минимальная сумма для обмена {method} {min_amount}",
            code="MIN_AMOUNT",
            status_code=422,
            params={"minAmount": min_amount, "method": method, "currency": currency_sell},
        )


def get_min_amount(method: str, currency: str) -> int | None:
    """Возвращает минимальную сумму для способа получения и валюты продажи."""
    limits = MIN_AMOUNT_BY_METHOD.get(method, {})
    normalized_currency = _normalize_min_amount_currency(currency)
    return limits.get(normalized_currency)


def _normalize_min_amount_currency(currency: str) -> str:
    """Вернуть валюту, по которой нужно искать лимит минимальной суммы."""
    normalized = currency.upper()
    if normalized == TOKEN_CURRENCY:
        return TOKEN_RATE_BASE_CURRENCY
    return normalized


def _resolve_rate_pair_key(
    exchange_service: ExchangeService,
    payload: MiniappOrderCreate,
) -> str | None:
    """Вернуть ключ пары в `Rates` для заявки, включая ATXG через USDT-базу."""
    if _is_aex_withdrawal(payload):
        buy = payload.currency_buy.upper()
        if buy not in CANONICAL_BUY_CURRENCIES:
            return None
        return f"{TOKEN_RATE_BASE_CURRENCY}{buy}"

    pair = exchange_service.normalize_pair(payload.currency_sell, payload.currency_buy)
    if pair is None:
        return None
    return "".join(pair)


def _is_aex_withdrawal(payload: MiniappOrderCreate) -> bool:
    """Проверить, что заявка выводит внутренний токен."""
    return payload.currency_sell.upper() == TOKEN_CURRENCY


def _normalize_token_currency(currency: str) -> str:
    normalized = currency.upper()
    if normalized == TOKEN_CURRENCY:
        return TOKEN_CURRENCY
    return normalized


async def _validate_aex_withdrawal_balance(
    db: AsyncSession,
    user_id: int,
    payload: MiniappOrderCreate,
) -> None:
    """Проверить лимит и доступный баланс перед резервированием ATXG."""
    if not _is_aex_withdrawal(payload):
        return

    wallet = await AexService().get_balance(db, user_id)
    config = await ConfigRepository(db).get_or_create()
    amount = Decimal(str(payload.amount_sell))

    if wallet.balance_available < config.aex_withdraw_limit:
        raise AntExException(
            "ATXG withdraw limit is not reached",
            code="ATXG_WITHDRAW_LIMIT_NOT_REACHED",
            status_code=422,
            params={
                "minAmount": str(config.aex_withdraw_limit),
                "available": str(wallet.balance_available),
                "currency": TOKEN_CURRENCY,
            },
        )

    if wallet.balance_available < amount:
        raise AntExException(
            "Insufficient ATXG balance",
            code="ATXG_INSUFFICIENT_BALANCE",
            status_code=422,
            params={
                "available": str(wallet.balance_available),
                "amount": str(amount),
                "currency": TOKEN_CURRENCY,
            },
        )
