# ruff: noqa: RUF001, RUF002
"""Сервисы miniapp API."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from sqlalchemy import select

from app.core.config import settings
from app.models.order import Order
from app.repositories.city import CityRepository
from app.repositories.config import ConfigRepository
from app.repositories.order import OrderRepository
from app.repositories.rate import RateRepository
from app.repositories.user import UserRepository
from app.schemas.city import build_city_out
from app.schemas.miniapp import (
    MiniappAexPayoutOption,
    MiniappAexReferralResponse,
    MiniappAexReferralsResponse,
    MiniappAexReferralUserItem,
    MiniappAexTransactionItem,
    MiniappAexTransactionsResponse,
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
    MiniappReferralProgramConfig,
    MiniappServiceItem,
    build_miniapp_manager_availability,
    build_miniapp_order_item,
    build_miniapp_profile_summary,
)
from app.schemas.rate import build_rate_out
from app.services.aex import (
    ORDER_WITHDRAW_DEBIT_REFERENCE,
    ORDER_WITHDRAW_HOLD_REFERENCE,
    ORDER_WITHDRAW_RELEASE_REFERENCE,
    AexService,
)
from app.services.aex_rate import AexRateService, rate_to_percent
from app.services.exchange import (
    COUNTRY_CURRENCY,
    COUNTRY_PRIORITY,
    HOME_RATE_PREVIEW_LIMIT,
    ExchangePairSnapshot,
    ExchangeQuote,
    ExchangeQuoteInput,
    ExchangeService,
    format_rate_value,
    get_client_rate,
)
from app.services.manager_working_hours import ManagerWorkingHoursService
from app.services.order_notifications import build_chat_url_for_user
from app.services.referral import ReferralService, build_referral_link
from app.telegram.i18n import get_translator

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


async def list_miniapp_orders(
    db,
    user_id: int,
    limit: int = 10,
    offset: int = 0,
) -> MiniappOrdersResponse:
    """Возвращает историю заявок текущего пользователя miniapp."""
    repository = OrderRepository(db)
    total = await repository.count_user_orders(user_id)
    orders = await repository.get_user_orders(user_id, limit=limit, offset=offset)
    return MiniappOrdersResponse(
        items=[build_miniapp_order_item(order) for order in orders],
        limit=limit,
        offset=offset,
        total=total,
        hasMore=offset + len(orders) < total,
    )


def _map_miniapp_aex_transaction_type(entry) -> str:
    if entry.reference_type == "referral":
        return "referral_reward"
    if entry.reference_type == "transfer":
        return "withdrawal"
    if entry.reference_type == ORDER_WITHDRAW_HOLD_REFERENCE:
        return "reserved"
    if entry.reference_type == ORDER_WITHDRAW_DEBIT_REFERENCE:
        return "debited"
    if entry.reference_type == ORDER_WITHDRAW_RELEASE_REFERENCE:
        return "refund"
    if entry.entry_type == "credit":
        return "bonus"
    return "adjustment"


def _extract_order_id(reference_id: str | None) -> int | None:
    if not reference_id:
        return None
    try:
        return int(reference_id)
    except ValueError:
        return None


async def _load_referral_order_numbers(db, entries) -> dict[int, str]:
    order_ids: set[int] = set()
    for entry in entries:
        if entry.reference_type not in {
            "referral",
            ORDER_WITHDRAW_HOLD_REFERENCE,
            ORDER_WITHDRAW_DEBIT_REFERENCE,
            ORDER_WITHDRAW_RELEASE_REFERENCE,
        }:
            continue
        order_id = _extract_order_id(entry.reference_id)
        if order_id is not None:
            order_ids.add(order_id)

    if not order_ids:
        return {}

    result = await db.execute(
        select(Order.id, Order.publicNumber).where(Order.id.in_(order_ids)),
    )
    return {order_id: public_number for order_id, public_number in result.all()}


def _build_miniapp_aex_transaction_description(
    entry,
    order_numbers: dict[int, str],
    *,
    locale: str | None = None,
) -> str:
    translate = get_translator(locale)
    order_id = _extract_order_id(entry.reference_id)
    public_number = order_numbers.get(order_id) if order_id is not None else None

    if entry.reference_type == "referral":
        if public_number:
            return translate("miniapp-aex-referral-reward-with-order", order_number=public_number)
        return translate("miniapp-aex-referral-reward")
    if entry.reference_type == ORDER_WITHDRAW_HOLD_REFERENCE:
        if public_number:
            return translate("miniapp-aex-withdraw-hold-with-order", order_number=public_number)
        return translate("miniapp-aex-withdraw-hold")
    if entry.reference_type == ORDER_WITHDRAW_DEBIT_REFERENCE:
        if public_number:
            return translate("miniapp-aex-withdraw-debit-with-order", order_number=public_number)
        return translate("miniapp-aex-withdraw-debit")
    if entry.reference_type == ORDER_WITHDRAW_RELEASE_REFERENCE:
        if public_number:
            return translate("miniapp-aex-withdraw-release-with-order", order_number=public_number)
        return translate("miniapp-aex-withdraw-release")

    return entry.description or ""


async def list_miniapp_aex_transactions(
    db,
    user_id: int,
    *,
    locale: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> MiniappAexTransactionsResponse:
    entries, total = await AexService().get_operations(db, user_id, limit=limit, offset=offset)
    referral_order_numbers = await _load_referral_order_numbers(db, entries)
    running_balance = Decimal("0")
    items: list[MiniappAexTransactionItem] = []
    for entry in reversed(entries):
        if entry.entry_type not in {"hold", "release"}:
            running_balance += entry.amount
        items.append(
            MiniappAexTransactionItem(
                id=entry.id,
                type=_map_miniapp_aex_transaction_type(entry),
                amount=float(entry.amount),
                balanceAfter=float(running_balance),
                description=_build_miniapp_aex_transaction_description(
                    entry,
                    referral_order_numbers,
                    locale=locale,
                ),
                createdAt=entry.createdAt,
            )
        )
    items.reverse()
    return MiniappAexTransactionsResponse(
        items=items,
        limit=limit,
        offset=offset,
        total=total,
        hasMore=offset + len(items) < total,
    )


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
                title="Доставка наличных",
                subtitle="Получение в городе",
                icon="payments",
            ),
            MiniappServiceItem(
                id="qrcode",
                title="Наличные по QR",
                subtitle="Выдача без выбора города",
                icon="qr_code_2",
            ),
            MiniappServiceItem(
                id="bank_account",
                title="Перевод на счёт",
                subtitle="В местном банке",
                icon="account_balance",
            ),
            MiniappServiceItem(
                id="pay_services",
                title="Оплата сервисов",
                subtitle="Платежи по реквизитам",
                icon="receipt_long",
            ),
        ],
        locations=[
            MiniappLocationItem(
                id=str(city.id),
                city=city.name,
                country=city.country.value,
                countryLabel=city.country.ru_name,
                countryFlag=city.country.flag,
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
        aexPayoutOptions=await _build_aex_payout_options(db),
        managerAvailability=build_miniapp_manager_availability(
            ManagerWorkingHoursService().get_availability(
                await ConfigRepository(db).get_or_create()
            )
        ),
    )


async def _build_aex_payout_options(db) -> list[MiniappAexPayoutOption]:
    """Строит безопасные итоговые курсы ATXG-выплаты для Mini App."""
    config = await ConfigRepository(db).get_or_create()
    aex_usdt_rate = float(config.aex_rate)
    options = [_build_aex_payout_option("USDT", aex_usdt_rate)]

    internal_rub_rate = await RateRepository(db).find_internal_by_currency("USDTRUB")
    if internal_rub_rate is not None:
        rub_rate = aex_usdt_rate * get_client_rate(internal_rub_rate)
        if rub_rate > 0:
            options.append(_build_aex_payout_option("RUB", rub_rate))
    return options


def _build_aex_payout_option(
    currency_buy: Literal["USDT", "RUB"],
    rate: float,
) -> MiniappAexPayoutOption:
    """Форматирует один рассчитанный вариант ATXG-выплаты."""
    rounded_rate = round(rate, 2)
    rate_display = format_rate_value(rounded_rate)
    return MiniappAexPayoutOption(
        currencyBuy=currency_buy,
        rate=rounded_rate,
        rateDisplay=rate_display,
        rateText=f"1 ATXG = {rate_display} {currency_buy}",
        availableMethods=["bank_account"],
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


async def get_miniapp_profile_screen(db, user) -> MiniappProfileScreenResponse:
    """Возвращает профиль в формате, который ожидает текущий экран miniapp."""
    manager = await UserRepository(db).get_manager()
    manager_chat_url = build_chat_url_for_user(manager) if manager is not None else None

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
                action="link" if manager_chat_url else "sheet",
                href=manager_chat_url,
            ),
        ],
        version="1.0.0",
        managerAvailability=build_miniapp_manager_availability(
            ManagerWorkingHoursService().get_availability(
                await ConfigRepository(db).get_or_create()
            )
        ),
    )


async def get_miniapp_aex_referral(db, user) -> MiniappAexReferralResponse:
    """Возвращает referral-контракт Mini App с готовой ссылкой для копирования."""
    referral_service = ReferralService()
    referral_code = await referral_service.get_or_create_referral_code(db, user)
    total_referrals, _ = await referral_service.get_referral_stats(db, user)
    config = await ConfigRepository(db).get_or_create()
    await db.commit()

    return MiniappAexReferralResponse(
        referralCode=referral_code,
        referralLink=build_referral_link(referral_code, settings.telegram_bot_username),
        totalReferrals=total_referrals,
        programConfig=MiniappReferralProgramConfig(
            referralPercent=config.referral_percent,
            referralMinWithdraw=config.referral_min_withdraw,
            referralMaxWithdraw=config.referral_max_withdraw,
            aexRate=config.aex_rate,
            aexWithdrawLimit=config.aex_withdraw_limit,
        ),
    )


async def list_miniapp_aex_referrals(
    db,
    user,
    *,
    limit: int = 20,
    offset: int = 0,
) -> MiniappAexReferralsResponse:
    """Возвращает безопасный список приглашенных рефералов текущего пользователя."""
    user_repo = UserRepository(db)
    referrals, total = await user_repo.get_referrals_paginated(user.id, limit=limit, offset=offset)
    _, total_accrued = await ReferralService().get_referral_stats(db, user)
    reward_percent = rate_to_percent(await AexRateService().get_effective_rate(db, user.id))

    return MiniappAexReferralsResponse(
        items=[
            MiniappAexReferralUserItem(
                id=referral.id,
                displayName=_build_referral_display_name(referral),
                username=referral.username,
                photoUrl=referral.photo_url,
                joinedAt=referral.createdAt,
                rewardPercent=reward_percent,
            )
            for referral in referrals
        ],
        limit=limit,
        offset=offset,
        total=total,
        hasMore=offset + len(referrals) < total,
        totalAccrued=total_accrued,
        rewardPercent=reward_percent,
    )


def _build_referral_display_name(user) -> str:
    display_name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    if display_name:
        return display_name
    if user.username:
        return f"@{user.username}"
    return "Пользователь AntEx"


def _build_rate_cards(snapshots: list[ExchangePairSnapshot]) -> list[MiniappRateCard]:
    """Преобразует доменные пары в карточки miniapp."""
    return [
        MiniappRateCard(
            id=snapshot.pair_id,
            label=snapshot.label,
            country=snapshot.country.value,
            countryLabel=snapshot.country.ru_name,
            countryFlag=snapshot.country.flag,
            fromCurrency=snapshot.currency_sell,
            toCurrency=snapshot.currency_buy,
            rate=snapshot.client_rate,
            calculationRate=snapshot.calculation_rate,
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
    seen: set[str] = set()
    for card in cards:
        for currency in (card.fromCurrency, card.toCurrency):
            if currency not in seen:
                seen.add(currency)
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
