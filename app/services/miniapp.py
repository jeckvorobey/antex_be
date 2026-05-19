# ruff: noqa: RUF001, RUF002
"""Сервисы miniapp API."""

from __future__ import annotations

from app.repositories.city import CityRepository
from app.repositories.order import OrderRepository
from app.schemas.city import build_city_out
from app.schemas.miniapp import (
    MiniappBanner,
    MiniappCalculatorState,
    MiniappCitiesResponse,
    MiniappCountryFilterItem,
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
from app.services.exchange import (
    COUNTRY_CURRENCY,
    COUNTRY_PRIORITY,
    HOME_RATE_PREVIEW_LIMIT,
    ExchangePairSnapshot,
    ExchangeQuote,
    ExchangeQuoteInput,
    ExchangeService,
)

DEFAULT_AMOUNT_SELL = 5000
DEFAULT_PAIR = ("RUB", "THB")
HOME_RATE_PRIORITY = (
    "rub-thb",
    "usdt-thb",
    "rub-vnd",
    "usdt-vnd",
    "rub-gel",
    "usdt-gel",
)


async def list_miniapp_cities(db) -> MiniappCitiesResponse:
    """Возвращает список городов для miniapp."""
    cities = await CityRepository(db).get_all()
    return MiniappCitiesResponse(items=[build_city_out(city) for city in cities])


async def list_miniapp_rates(db) -> MiniappRatesResponse:
    """Возвращает пользовательские итоговые курсы для обратной совместимости miniapp."""
    rates = await ExchangeService().load_rates(db)
    return MiniappRatesResponse(items=[build_rate_out(rate) for rate in rates])


async def list_miniapp_orders(db, user_id: int) -> MiniappOrdersResponse:
    """Возвращает историю заявок текущего пользователя miniapp."""
    orders = await OrderRepository(db).get_user_orders(user_id, limit=100)
    return MiniappOrdersResponse(items=[build_miniapp_order_item(order) for order in orders])


async def get_miniapp_home(db, user) -> MiniappHomeResponse:
    """Собирает backend-driven данные главного экрана miniapp."""
    exchange_service = ExchangeService()
    rates = await exchange_service.load_rates(db)
    cities = await CityRepository(db).get_all()
    snapshots = exchange_service.build_pair_snapshots(rates)
    featured = _build_home_rate_cards(snapshots)

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
        countries=[
            MiniappCountryFilterItem(
                id=country.value,
                label=country.ru_name,
                currency=COUNTRY_CURRENCY[country],
                code=country.code,
                flag=country.flag,
            )
            for country in COUNTRY_PRIORITY
        ],
        rates=MiniappRatesSection(
            featured=featured,
            chips=exchange_service.build_home_chips(snapshots),
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
                country=city.country.value,
                countryLabel=city.country.ru_name,
                hours="Ежедневно",
                accent="ocean" if index % 2 == 0 else "gold",
            )
            for index, city in enumerate(cities)
        ],
    )


async def get_miniapp_exchange(db) -> MiniappExchangeScreenResponse:
    """Собирает начальное состояние экрана обмена miniapp."""
    exchange_service = ExchangeService()
    snapshots = await exchange_service.list_pair_snapshots(db)
    featured = _build_rate_cards(snapshots)
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
    """Рассчитывает quote через единый exchange-domain."""
    quote = await ExchangeService().get_quote(
        db,
        ExchangeQuoteInput(
            currency_sell=currency_sell,
            currency_buy=currency_buy,
            amount_sell=amount_sell,
        ),
    )
    return _build_quote_response(quote)


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


def _build_rate_cards(snapshots: list[ExchangePairSnapshot]) -> list[MiniappRateCard]:
    """Преобразует доменные пары в карточки miniapp."""
    return [
        MiniappRateCard(
            id=snapshot.pair_id,
            label=snapshot.label,
            country=snapshot.country.value,
            countryLabel=snapshot.country.ru_name,
            fromCurrency=snapshot.currency_sell,
            toCurrency=snapshot.currency_buy,
            rate=snapshot.client_rate,
            rateDisplay=snapshot.rate_display,
            rateText=snapshot.rate_text,
            amountSellExample=snapshot.amount_sell_example,
            amountBuyExample=snapshot.amount_buy_example,
            updatedAt=snapshot.updated_at,
            availableMethods=snapshot.available_methods,
        )
        for snapshot in snapshots
    ]


def _build_home_rate_cards(snapshots: list[ExchangePairSnapshot]) -> list[MiniappRateCard]:
    """Строит карточки курсов для главной с фиксированным порядком превью."""
    cards = _build_rate_cards(snapshots)
    priority = {pair_id: index for index, pair_id in enumerate(HOME_RATE_PRIORITY)}
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


def _build_quote_response(quote: ExchangeQuote) -> MiniappQuoteResponse:
    return MiniappQuoteResponse(
        currencySell=quote.currency_sell,
        currencyBuy=quote.currency_buy,
        amountSell=quote.amount_sell,
        amountBuy=quote.amount_buy,
        rate=quote.rate,
        rateDisplay=quote.rate_display,
        rateText=quote.rate_text,
        updatedAt=quote.updated_at,
        availableMethods=quote.available_methods,
    )
