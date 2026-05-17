# ruff: noqa: RUF001, RUF002
"""Сервисы miniapp API."""

from __future__ import annotations

from app.repositories.city import CityRepository
from app.repositories.order import OrderRepository
from app.repositories.rate import RateRepository
from app.schemas.city import build_city_out
from app.schemas.miniapp import (
    MiniappBanner,
    MiniappCalculatorState,
    MiniappCitiesResponse,
    MiniappExchangeScreenResponse,
    MiniappHomeResponse,
    MiniappLocationItem,
    MiniappMenuItem,
    MiniappOrdersResponse,
    MiniappProfileScreenResponse,
    MiniappQuickAction,
    MiniappQuoteResponse,
    MiniappRateCard,
    MiniappRatesResponse,
    MiniappRatesSection,
    MiniappServiceItem,
    build_miniapp_order_item,
    build_miniapp_profile_summary,
)
from app.schemas.rate import build_rate_out
from app.services.rate import get_client_rate

DEFAULT_AMOUNT_SELL = 5000
DEFAULT_PAIR = ("RUB", "THB")
HOME_RATE_PREVIEW_LIMIT = 3
HOME_RATE_PRIORITY = ("usdt-thb", "usdt-vnd", "usdt-gel")
HOME_CHIP_PRIORITY = ("USDT", "THB", "RUB", "GEL", "VND")
METHODS_BY_BUY_CURRENCY = {
    "THB": ["cash"],
    "GEL": ["cash"],
    "VND": ["cash"],
    "USDT": ["wallet"],
    "RUB": ["card"],
}


async def list_miniapp_cities(db) -> MiniappCitiesResponse:
    """Возвращает список городов для miniapp."""
    cities = await CityRepository(db).get_all()
    return MiniappCitiesResponse(items=[build_city_out(city) for city in cities])


async def list_miniapp_rates(db) -> MiniappRatesResponse:
    """Возвращает пользовательские итоговые курсы для обратной совместимости miniapp."""
    rates = await RateRepository(db).get_all()
    return MiniappRatesResponse(items=[build_rate_out(rate) for rate in rates])


async def list_miniapp_orders(db, user_id: int) -> MiniappOrdersResponse:
    """Возвращает историю заявок текущего пользователя miniapp."""
    orders = await OrderRepository(db).get_user_orders(user_id, limit=100)
    return MiniappOrdersResponse(items=[build_miniapp_order_item(order) for order in orders])


async def get_miniapp_home(db, user) -> MiniappHomeResponse:
    """Собирает backend-driven данные главного экрана miniapp."""
    rates = await RateRepository(db).get_all()
    cities = await CityRepository(db).get_all()
    featured = _build_home_rate_cards(rates)

    return MiniappHomeResponse(
        profile=build_miniapp_profile_summary(user),
        quickActions=[
            MiniappQuickAction(
                id="exchange",
                title="Обмен",
                subtitle="Рассчитать заявку",
                icon="currency_exchange",
                route="/exchange",
                tone="primary",
            ),
            MiniappQuickAction(
                id="history",
                title="История",
                subtitle="Ваши заявки",
                icon="history",
                route="/history",
                tone="neutral",
            ),
            MiniappQuickAction(
                id="profile",
                title="Профиль",
                subtitle="Данные клиента",
                icon="person_outline",
                route="/profile",
                tone="neutral",
            ),
            MiniappQuickAction(
                id="support",
                title="Поддержка",
                subtitle="Связаться с нами",
                icon="support_agent",
                tone="neutral",
            ),
        ],
        rates=MiniappRatesSection(
            featured=featured,
            chips=_build_home_currency_chips(featured),
            previewLimit=HOME_RATE_PREVIEW_LIMIT,
            updatedAt=max((rate.updatedAt for rate in rates), default=None),
        ),
        banner=MiniappBanner(
            title="Приведи друга и получи бонус",
            actionLabel="Подробнее",
        ),
        services=[
            MiniappServiceItem(
                id="cash",
                title="Наличные",
                subtitle="Получение в городе",
                icon="payments",
            ),
            MiniappServiceItem(
                id="wallet",
                title="USDT",
                subtitle="Перевод на кошелёк",
                icon="account_balance_wallet",
            ),
        ],
        locations=[
            MiniappLocationItem(
                id=str(city.id),
                city=city.name,
                hours="Ежедневно",
                accent="ocean" if index % 2 == 0 else "gold",
            )
            for index, city in enumerate(cities)
        ],
    )


async def get_miniapp_exchange(db) -> MiniappExchangeScreenResponse:
    """Собирает начальное состояние экрана обмена miniapp."""
    rates = await RateRepository(db).get_all()
    featured = _build_rate_cards(rates)
    quote = await calculate_miniapp_quote(
        db,
        DEFAULT_PAIR[0],
        DEFAULT_PAIR[1],
        DEFAULT_AMOUNT_SELL,
    )

    return MiniappExchangeScreenResponse(
        calculator=MiniappCalculatorState(
            fromCurrency=DEFAULT_PAIR[0],
            toCurrency=DEFAULT_PAIR[1],
            amountSell=DEFAULT_AMOUNT_SELL,
        ),
        chips=_build_currency_chips(featured),
        pairs=featured,
        quote=quote,
    )


async def calculate_miniapp_quote(
    db,
    currency_sell: str,
    currency_buy: str,
    amount_sell: int,
) -> MiniappQuoteResponse:
    """Рассчитывает quote по актуальному серверному курсу."""
    from app.exceptions import AntExException

    sell = currency_sell.upper()
    buy = currency_buy.upper()
    if sell == buy or amount_sell <= 0:
        raise AntExException(
            "Unsupported currency pair",
            code="UNSUPPORTED_PAIR",
            status_code=422,
        )

    rates = await RateRepository(db).get_all()
    if not rates:
        raise AntExException(
            "Rate is unavailable",
            code="RATE_UNAVAILABLE",
            status_code=503,
        )

    rate, updated_at = _resolve_pair_rate(rates, sell, buy)
    if rate is None or updated_at is None:
        raise AntExException(
            "Unsupported currency pair",
            code="UNSUPPORTED_PAIR",
            status_code=422,
        )

    amount_buy = amount_sell * rate
    return MiniappQuoteResponse(
        currencySell=sell,
        currencyBuy=buy,
        amountSell=amount_sell,
        amountBuy=round(amount_buy, 8),
        rate=rate,
        rateText=f"1 {sell} = {_format_rate(rate)} {buy}",
        updatedAt=updated_at,
        availableMethods=METHODS_BY_BUY_CURRENCY.get(buy, ["cash"]),
    )


async def get_miniapp_profile_screen(user) -> MiniappProfileScreenResponse:
    """Возвращает профиль в формате, который ожидает текущий экран miniapp."""
    return MiniappProfileScreenResponse(
        user=build_miniapp_profile_summary(user),
        menu=[
            MiniappMenuItem(
                id="history",
                title="История операций",
                icon="history",
                action="route",
                route="/history",
            ),
            MiniappMenuItem(
                id="support",
                title="Поддержка",
                icon="support_agent",
                action="sheet",
            ),
        ],
        version="1.0.0",
    )


def _build_rate_cards(rates) -> list[MiniappRateCard]:
    """Преобразует сохранённые курсы в карточки поддерживаемых пар."""
    cards: list[MiniappRateCard] = []
    for rate in rates:
        parsed = _parse_pair(rate.currency)
        if not parsed:
            continue
        sell, buy = parsed
        amount_sell = 5000 if sell == "RUB" else 100
        cards.append(
            MiniappRateCard(
                id=f"{sell.lower()}-{buy.lower()}",
                label=f"{sell}/{buy}",
                fromCurrency=sell,
                toCurrency=buy,
                rate=get_client_rate(rate),
                rateText=f"1 {sell} = {_format_rate(get_client_rate(rate))} {buy}",
                amountSellExample=amount_sell,
                amountBuyExample=round(amount_sell * get_client_rate(rate), 8),
                updatedAt=rate.updatedAt,
            )
        )
    return cards


def _build_home_rate_cards(rates) -> list[MiniappRateCard]:
    """Строит карточки курсов для главной с фиксированным порядком превью."""
    cards = _build_rate_cards(rates)
    priority = {
        pair_id: index
        for index, pair_id in enumerate(HOME_RATE_PRIORITY)
    }
    return sorted(
        cards,
        key=lambda card: (
            priority.get(card.id, len(priority)),
            card.id,
        ),
    )


def _build_currency_chips(cards: list[MiniappRateCard]) -> list[str]:
    """Возвращает валюты, которые встречаются в карточках курсов."""
    currencies: list[str] = []
    for card in cards:
        for currency in (card.fromCurrency, card.toCurrency):
            if currency not in currencies:
                currencies.append(currency)
    return currencies


def _build_home_currency_chips(cards: list[MiniappRateCard]) -> list[str]:
    """Возвращает стабильный порядок валют для home-блока."""
    available = set(_build_currency_chips(cards))
    return [currency for currency in HOME_CHIP_PRIORITY if currency in available]


def _parse_pair(currency: str) -> tuple[str, str] | None:
    """Разбирает pair-key вида RUBTHB или USDTTHB."""
    supported = ("USDT", "RUB", "THB", "GEL", "VND")
    upper = currency.upper()
    for sell in supported:
        if not upper.startswith(sell):
            continue
        buy = upper.removeprefix(sell)
        if buy in supported and buy != sell:
            return sell, buy
    return None


def _resolve_pair_rate(rates, sell: str, buy: str) -> tuple[float | None, object | None]:
    """Находит прямой курс или обратный курс по сохранённой паре."""
    direct_key = f"{sell}{buy}"
    reverse_key = f"{buy}{sell}"
    for rate in rates:
        currency = rate.currency.upper()
        if currency == direct_key:
            return get_client_rate(rate), rate.updatedAt
        client_rate = get_client_rate(rate)
        if currency == reverse_key and client_rate:
            return 1 / client_rate, rate.updatedAt
    return None, None


def _format_rate(rate: float) -> str:
    """Форматирует курс для компактного отображения в miniapp."""
    return f"{rate:.4f}" if rate < 1 else f"{rate:.2f}"
