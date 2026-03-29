"""Сервисы miniapp API."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.order import MethodGet, OrderStatus
from app.exceptions import AntExException
from app.models.user import User
from app.repositories.bank import BankRepository
from app.repositories.order import OrderRepository
from app.schemas.miniapp import (
    MiniappBankSummary,
    MiniappBanner,
    MiniappCalculatorState,
    MiniappExchangeScreenResponse,
    MiniappHomeResponse,
    MiniappLocationItem,
    MiniappMenuItem,
    MiniappOrderCreate,
    MiniappOrderItem,
    MiniappOrdersResponse,
    MiniappProfileResponse,
    MiniappProfileSummary,
    MiniappQuickAction,
    MiniappQuoteResponse,
    MiniappRateCard,
    MiniappRatesSection,
    MiniappServiceItem,
)

QUOTE_METHODS = [MethodGet.CASH, MethodGet.QR, MethodGet.RS]
HOME_SERVICE_ITEMS = [
    MiniappServiceItem(
        id="verification",
        title="Верификация",
        subtitle="Подтверждение профиля",
        icon="mdi-shield-check-outline",
    ),
    MiniappServiceItem(
        id="guide",
        title="Путеводитель",
        subtitle="Полезные места и сервисы",
        icon="mdi-map-marker-path",
    ),
    MiniappServiceItem(
        id="atm",
        title="Найти ATM",
        subtitle="Ближайшие банкоматы",
        icon="mdi-cash-fast",
    ),
    MiniappServiceItem(
        id="partner",
        title="Кабинет партнёра",
        subtitle="Приводите клиентов",
        icon="mdi-account-tie-outline",
    ),
]
HOME_LOCATIONS = [
    MiniappLocationItem(
        id="bang-tao",
        city="Bang Tao",
        hours="10:00 - 21:00",
        accent="ocean",
    ),
    MiniappLocationItem(
        id="rawai",
        city="Rawai",
        hours="10:00 - 22:00",
        accent="gold",
    ),
]


def build_profile_summary(user: User) -> MiniappProfileSummary:
    """Строит компактное представление пользователя для miniapp."""
    full_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
    return MiniappProfileSummary(
        id=user.id,
        displayName=full_name or user.username or f"User {user.id}",
        username=user.username,
        isPremium=user.is_premium,
        languageCode=(user.language_code or "ru").split("-", 1)[0],
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _format_rate_text(rate: float, sell: str, buy: str) -> str:
    if sell == "RUB" and buy == "THB":
        return f"{rate:.1f} ฿ за 1 ₽"
    if sell == "USDT" and buy == "THB":
        return f"{rate:.1f} ฿ за 1 USDT"
    if sell == "RUB" and buy == "USDT":
        return f"{rate:.4f} USDT за 1 ₽"
    return f"{rate:.4f} {buy} за 1 {sell}"


def resolve_pair_rate(snapshot: dict[str, float], currency_sell: str, currency_buy: str) -> float:
    """Возвращает курс для поддерживаемой валютной пары miniapp."""
    currency_sell = currency_sell.upper()
    currency_buy = currency_buy.upper()

    if currency_sell == "RUB" and currency_buy == "THB":
        return snapshot["RUBTHB"]
    if currency_sell == "USDT" and currency_buy == "THB":
        return snapshot["USDTTHB"]
    if currency_sell == "RUB" and currency_buy == "USDT":
        usdtrub = snapshot["USDTRUB"]
        if usdtrub <= 0:
            return 0.0
        return 1 / usdtrub

    raise AntExException(
        "Unsupported currency pair",
        code="UNSUPPORTED_PAIR",
        status_code=400,
        params={"currencySell": currency_sell, "currencyBuy": currency_buy},
    )


def calculate_quote(
    snapshot: dict[str, float],
    currency_sell: str,
    currency_buy: str,
    amount_sell: int,
) -> MiniappQuoteResponse:
    """Рассчитывает quote для miniapp и нормализует округление по парам."""
    rate = resolve_pair_rate(snapshot, currency_sell, currency_buy)
    if rate <= 0:
        raise AntExException("Exchange rate unavailable", code="RATE_UNAVAILABLE", status_code=503)

    if currency_sell == "RUB" and currency_buy == "USDT":
        amount_buy: float = round(amount_sell * rate, 2)
    else:
        amount_buy = float(round(amount_sell * rate))

    return MiniappQuoteResponse(
        currencySell=currency_sell,
        currencyBuy=currency_buy,
        amountSell=amount_sell,
        amountBuy=amount_buy,
        rate=rate,
        rateText=_format_rate_text(rate, currency_sell, currency_buy),
        updatedAt=_now(),
        availableMethods=QUOTE_METHODS,
    )


def build_rate_card(
    *,
    card_id: str,
    currency_sell: str,
    currency_buy: str,
    amount_sell_example: int,
    snapshot: dict[str, float],
) -> MiniappRateCard:
    """Готовит карточку курса из snapshot и примерной суммы продажи."""
    quote = calculate_quote(snapshot, currency_sell, currency_buy, amount_sell_example)
    return MiniappRateCard(
        id=card_id,
        label=f"{currency_sell} -> {currency_buy}",
        fromCurrency=currency_sell,
        toCurrency=currency_buy,
        rate=quote.rate,
        rateText=quote.rateText,
        amountSellExample=amount_sell_example,
        amountBuyExample=quote.amountBuy,
        updatedAt=quote.updatedAt,
    )


def build_pairs(snapshot: dict[str, float]) -> list[MiniappRateCard]:
    """Возвращает фиксированный список отображаемых валютных пар miniapp."""
    return [
        build_rate_card(
            card_id="rub-thb",
            currency_sell="RUB",
            currency_buy="THB",
            amount_sell_example=5000,
            snapshot=snapshot,
        ),
        build_rate_card(
            card_id="rub-usdt",
            currency_sell="RUB",
            currency_buy="USDT",
            amount_sell_example=5000,
            snapshot=snapshot,
        ),
        build_rate_card(
            card_id="usdt-thb",
            currency_sell="USDT",
            currency_buy="THB",
            amount_sell_example=150,
            snapshot=snapshot,
        ),
    ]


def build_home_response(user: User, snapshot: dict[str, float]) -> MiniappHomeResponse:
    """Собирает backend-driven payload для главного экрана miniapp."""
    updated_at = _now()
    return MiniappHomeResponse(
        profile=build_profile_summary(user),
        quickActions=[
            MiniappQuickAction(
                id="desktop",
                title="На рабочий стол",
                subtitle="",
                icon="mdi-monitor-dashboard",
                tone="gold",
            ),
            MiniappQuickAction(
                id="benefits",
                title="Плюсы",
                subtitle="",
                icon="mdi-diamond-stone",
            ),
            MiniappQuickAction(
                id="reviews",
                title="Отзывы",
                subtitle="",
                icon="mdi-message-text-outline",
            ),
            MiniappQuickAction(
                id="bonuses",
                title="Бонусы",
                subtitle="",
                icon="mdi-star-four-points-outline",
                tone="gold",
            ),
        ],
        rates=MiniappRatesSection(
            featured=build_pairs(snapshot),
            chips=["Все", "Таиланд", "Бали", "Дубай", "Китай"],
            updatedAt=updated_at,
            allowance=snapshot["allowance"],
        ),
        banner=MiniappBanner(
            title="Приведи друга и получи бонус",
            actionLabel="Подробнее",
        ),
        services=HOME_SERVICE_ITEMS,
        locations=HOME_LOCATIONS,
    )


def build_exchange_screen(snapshot: dict[str, float]) -> MiniappExchangeScreenResponse:
    """Собирает экран обмена со стартовым калькулятором и доступными парами."""
    default_quote = calculate_quote(snapshot, "RUB", "THB", 5000)
    return MiniappExchangeScreenResponse(
        calculator=MiniappCalculatorState(
            fromCurrency="RUB",
            toCurrency="THB",
            amountSell=5000,
        ),
        chips=["RUB", "USDT"],
        pairs=build_pairs(snapshot),
        quote=default_quote,
    )


def build_order_item(order) -> MiniappOrderItem:
    """Преобразует доменную заявку в DTO miniapp."""
    bank = order.bank
    if bank is None:
        raise AntExException("Order bank is missing", code="BANK_NOT_FOUND", status_code=500)

    return MiniappOrderItem(
        id=order.id,
        currencySell=order.currencySell,
        amountSell=order.amountSell,
        currencyBuy=order.currencyBuy,
        amountBuy=order.amountBuy,
        rate=order.rate,
        status=order.status,
        methodGet=order.methodGet,
        contactTelegram=order.contactTelegram,
        createdAt=order.createdAt,
        bank=MiniappBankSummary(
            id=bank.id,
            code=bank.code,
            name=bank.name,
        ),
    )


def build_orders_response(orders: list) -> MiniappOrdersResponse:
    """Собирает ответ истории заявок miniapp."""
    return MiniappOrdersResponse(items=[build_order_item(order) for order in orders])


def build_profile_response(user: User) -> MiniappProfileResponse:
    """Возвращает профиль пользователя и меню вторичных действий."""
    return MiniappProfileResponse(
        user=build_profile_summary(user),
        menu=[
            MiniappMenuItem(
                id="orders",
                title="Мои заявки",
                icon="mdi-file-document-outline",
                action="route",
                route="/history",
            ),
            MiniappMenuItem(
                id="notifications",
                title="Уведомления",
                icon="mdi-bell-outline",
                action="sheet",
            ),
            MiniappMenuItem(
                id="about",
                title="О сервисе",
                icon="mdi-information-outline",
                action="sheet",
            ),
            MiniappMenuItem(
                id="support",
                title="Поддержка",
                icon="mdi-message-text-outline",
                action="link",
                href="https://t.me/antex_support",
            ),
        ],
        version="1.0.0",
    )


async def create_miniapp_order(
    db: AsyncSession,
    user: User,
    body: MiniappOrderCreate,
    snapshot: dict[str, float],
) -> MiniappOrderItem:
    """Создает miniapp-заявку с серверной валидацией и расчетом quote."""
    order_repo = OrderRepository(db)
    currency_sell = body.currencySell.upper()
    currency_buy = body.currencyBuy.upper()

    existing = await order_repo.check_open(user.id)
    if existing:
        raise AntExException(
            "User already has an open order",
            code="ORDER_ALREADY_EXISTS",
            status_code=409,
        )

    quote = calculate_quote(snapshot, currency_sell, currency_buy, body.amountSell)

    bank = next(iter(await BankRepository(db).get_all()), None)
    if bank is None:
        raise AntExException("No bank available", code="BANK_NOT_FOUND", status_code=404)

    created = await order_repo.create(
        UserId=user.id,
        BankId=bank.id,
        currencySell=currency_sell,
        amountSell=body.amountSell,
        currencyBuy=currency_buy,
        amountBuy=quote.amountBuy,
        rate=quote.rate,
        methodGet=body.methodGet or MethodGet.CASH,
        status=OrderStatus.NEW,
        contactTelegram=body.contactTelegram,
    )
    await db.refresh(created, attribute_names=["bank"])
    return build_order_item(created)
