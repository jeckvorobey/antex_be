"""Единый доменный сервис обмена.

SSOT для:
- пользовательских и административных представлений курсов;
- расчёта quote по любой поддерживаемой паре;
- форматирования значений курса для UI и бота.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.country import Country
from app.exceptions import AntExException
from app.models.rate import Rate
from app.repositories.rate import RateRepository
from app.services.rate_calculator import apply_margin_to_rate

RATE_PRECISION = 2
HOME_RATE_PREVIEW_LIMIT = 3
FEATURED_PAIR_PRIORITY = ("rub-thb", "usdt-thb", "usdt-gel")
HOME_CHIP_PRIORITY = ("USDT", "THB", "RUB", "GEL", "VND")
COUNTRY_BY_BUY_CURRENCY = {
    "THB": Country.THAILAND,
    "VND": Country.VIETNAM,
    "GEL": Country.GEORGIA,
}
COUNTRY_CURRENCY = {
    Country.THAILAND: "THB",
    Country.VIETNAM: "VND",
    Country.GEORGIA: "GEL",
}
COUNTRY_PRIORITY = (
    Country.THAILAND,
    Country.VIETNAM,
    Country.GEORGIA,
)
COUNTRY_METHODS = {
    Country.THAILAND: ["qrcode", "cash", "bank_account", "pay_services"],
    Country.VIETNAM: ["qrcode", "cash", "bank_account", "pay_services"],
    Country.GEORGIA: ["qrcode", "cash", "bank_account", "pay_services"],
}
DEFAULT_METHODS_BY_BUY_CURRENCY = {
    "USDT": ["wallet"],
    "RUB": ["card"],
}
SUPPORTED_CURRENCIES = ("USDT", "RUB", "THB", "GEL", "VND")
CANONICAL_SELL_CURRENCIES = frozenset({"RUB", "USDT"})
CANONICAL_BUY_CURRENCIES = frozenset({"THB", "GEL", "VND"})
REVERSED_DISPLAY_PAIRS = frozenset({"RUBTHB", "RUBGEL"})


def round_rate_value(rate: float) -> float:
    return round(rate, RATE_PRECISION)


def format_rate_value(rate: float) -> str:
    return f"{round_rate_value(rate):.{RATE_PRECISION}f}"


def is_rub_cross_pair(currency: str) -> bool:
    return currency.upper().startswith("RUB") and currency.upper() != "RUB"


def get_client_rate(rate: Rate) -> float:
    return round_rate_value(apply_margin_to_rate(rate.price, rate.margin))


def should_reverse_display_pair(currency: str) -> bool:
    return currency.upper() in REVERSED_DISPLAY_PAIRS


def get_display_pair(rate: Rate) -> tuple[str, str]:
    parsed = ExchangeService().parse_pair(rate.currency)
    if parsed is None:
        raise ExchangeService.unsupported_pair_error()
    sell, buy = parsed
    if should_reverse_display_pair(rate.currency):
        return buy, sell
    return sell, buy


def get_display_base_rate(rate: Rate) -> float:
    if should_reverse_display_pair(rate.currency) and rate.price:
        return 1 / rate.price
    return rate.price


def get_display_final_rate(rate: Rate) -> float:
    if should_reverse_display_pair(rate.currency):
        direct_client_rate = apply_margin_to_rate(rate.price, rate.margin)
        if direct_client_rate <= 0:
            return 0.0
        return round_rate_value(1 / direct_client_rate)
    return get_client_rate(rate)


def get_admin_base_rate(rate: Rate) -> float:
    return get_display_base_rate(rate)


def get_admin_final_rate(rate: Rate) -> float:
    return get_display_final_rate(rate)


@dataclass(frozen=True)
class ExchangeQuoteInput:
    currency_sell: str
    currency_buy: str
    amount_sell: int


@dataclass(frozen=True)
class ExchangeQuote:
    currency_sell: str
    currency_buy: str
    amount_sell: int
    amount_buy: float
    rate: float
    rate_display: str
    rate_text: str
    updated_at: datetime
    available_methods: list[str]


@dataclass(frozen=True)
class ExchangePairSnapshot:
    pair_id: str
    label: str
    currency_sell: str
    currency_buy: str
    country: Country
    base_rate: float
    client_rate: float
    calculation_rate: float
    rate_display: str
    rate_text: str
    amount_sell_example: int
    amount_buy_example: float
    updated_at: datetime
    available_methods: list[str]


class ExchangeService:
    """Доменный сервис обмена без привязки к конкретному клиенту."""

    async def load_rates(self, db: AsyncSession) -> list[Rate]:
        return await RateRepository(db).get_all()

    async def list_pair_snapshots(self, db: AsyncSession) -> list[ExchangePairSnapshot]:
        return self.build_pair_snapshots(await self.load_rates(db))

    async def get_quote(self, db: AsyncSession, payload: ExchangeQuoteInput) -> ExchangeQuote:
        return self.build_quote(await self.load_rates(db), payload)

    async def get_featured_pair_snapshots(
        self,
        db: AsyncSession,
    ) -> list[ExchangePairSnapshot]:
        return self.build_featured_pair_snapshots(await self.load_rates(db))

    def build_pair_snapshots(self, rates: list[Rate]) -> list[ExchangePairSnapshot]:
        snapshots: list[ExchangePairSnapshot] = []
        for rate in rates:
            parsed = self.parse_pair(rate.currency)
            if not parsed:
                continue
            sell, buy = parsed
            if not self.is_canonical_pair(sell, buy):
                continue
            quote_rate = get_client_rate(rate)
            display_rate = get_display_final_rate(rate)
            display_sell, display_buy = get_display_pair(rate)
            amount_sell = 5000 if sell == "RUB" else 100
            snapshots.append(
                ExchangePairSnapshot(
                    pair_id=f"{sell.lower()}-{buy.lower()}",
                    label=f"{sell}/{buy}",
                    currency_sell=sell,
                    currency_buy=buy,
                    country=rate.country,
                    base_rate=rate.price,
                    client_rate=display_rate,
                    calculation_rate=quote_rate,
                    rate_display=format_rate_value(display_rate),
                    rate_text=(
                        f"1 {display_sell} = {format_rate_value(display_rate)} {display_buy}"
                    ),
                    amount_sell_example=amount_sell,
                    amount_buy_example=round(amount_sell * quote_rate, RATE_PRECISION),
                    updated_at=rate.updatedAt,
                    available_methods=self.get_methods_for_currency(buy),
                )
            )
        return snapshots

    def build_featured_pair_snapshots(self, rates: list[Rate]) -> list[ExchangePairSnapshot]:
        snapshots = self.build_display_pair_snapshots(rates)
        priority = {pair_id: index for index, pair_id in enumerate(FEATURED_PAIR_PRIORITY)}
        return sorted(
            snapshots,
            key=lambda snapshot: (
                priority.get(snapshot.pair_id, len(priority)),
                snapshot.pair_id,
            ),
        )

    def build_display_pair_snapshots(self, rates: list[Rate]) -> list[ExchangePairSnapshot]:
        """Строит snapshots в display-ориентации для admin/telegram readers."""
        snapshots: list[ExchangePairSnapshot] = []
        for rate in rates:
            parsed = self.parse_pair(rate.currency)
            if not parsed:
                continue
            original_sell, original_buy = parsed
            try:
                sell, buy = get_display_pair(rate)
            except AntExException:
                continue
            client_rate = get_display_final_rate(rate)
            amount_sell = 5000 if sell == "RUB" else 100
            snapshots.append(
                ExchangePairSnapshot(
                    pair_id=f"{original_sell.lower()}-{original_buy.lower()}",
                    label=f"{sell}/{buy}",
                    currency_sell=sell,
                    currency_buy=buy,
                    country=rate.country,
                    base_rate=get_display_base_rate(rate),
                    client_rate=client_rate,
                    calculation_rate=client_rate,
                    rate_display=format_rate_value(client_rate),
                    rate_text=f"1 {sell} = {format_rate_value(client_rate)} {buy}",
                    amount_sell_example=amount_sell,
                    amount_buy_example=round(amount_sell * client_rate, RATE_PRECISION),
                    updated_at=rate.updatedAt,
                    available_methods=self.get_methods_for_currency(buy),
                )
            )
        return snapshots

    def build_quote(self, rates: list[Rate], payload: ExchangeQuoteInput) -> ExchangeQuote:
        pair = self.normalize_pair(payload.currency_sell, payload.currency_buy)
        if pair is None or payload.amount_sell <= 0:
            raise self.unsupported_pair_error()
        sell, buy = pair
        if not rates:
            raise self.rate_unavailable_error()

        rate_model = self.build_rate_index(rates).get(f"{sell}{buy}")
        if rate_model is None:
            raise self.unsupported_pair_error()

        rate = get_client_rate(rate_model)
        amount_buy = round(payload.amount_sell * rate, RATE_PRECISION)
        return ExchangeQuote(
            currency_sell=sell,
            currency_buy=buy,
            amount_sell=payload.amount_sell,
            amount_buy=amount_buy,
            rate=rate,
            rate_display=format_rate_value(rate),
            rate_text=f"1 {sell} = {format_rate_value(rate)} {buy}",
            updated_at=rate_model.updatedAt,
            available_methods=self.get_methods_for_currency(buy),
        )

    def build_home_chips(self, pair_snapshots: list[ExchangePairSnapshot]) -> list[str]:
        available = {
            currency
            for snapshot in pair_snapshots
            for currency in (snapshot.currency_sell, snapshot.currency_buy)
        }
        return [currency for currency in HOME_CHIP_PRIORITY if currency in available]

    def build_supported_pairs(
        self,
        pair_snapshots: list[ExchangePairSnapshot],
    ) -> dict[str, list[str]]:
        supported: dict[str, list[str]] = {}
        for snapshot in pair_snapshots:
            supported.setdefault(snapshot.currency_sell, [])
            if snapshot.currency_buy not in supported[snapshot.currency_sell]:
                supported[snapshot.currency_sell].append(snapshot.currency_buy)
        return supported

    def get_methods_for_currency(self, currency_buy: str) -> list[str]:
        country = COUNTRY_BY_BUY_CURRENCY.get(currency_buy.upper())
        return self.get_methods_for_country(country, currency_buy)

    def get_methods_for_country(
        self,
        country: Country | None,
        currency_buy: str | None = None,
    ) -> list[str]:
        if country is not None:
            return list(COUNTRY_METHODS.get(country, ["qrcode", "cash"]))
        if currency_buy is None:
            return ["cash"]
        return list(DEFAULT_METHODS_BY_BUY_CURRENCY.get(currency_buy.upper(), ["cash"]))

    def resolve_pair_rate(
        self,
        rates: list[Rate],
        sell: str,
        buy: str,
    ) -> tuple[float | None, datetime | None]:
        direct_key = f"{sell}{buy}"
        rate = self.build_rate_index(rates).get(direct_key)
        if rate is None:
            return None, None
        return get_client_rate(rate), rate.updatedAt

    @staticmethod
    def build_rate_index(rates: list[Rate]) -> dict[str, Rate]:
        indexed: dict[str, Rate] = {}
        for rate in rates:
            indexed.setdefault(rate.currency.upper(), rate)
        return indexed

    def normalize_pair(self, currency_sell: str, currency_buy: str) -> tuple[str, str] | None:
        sell = currency_sell.upper()
        buy = currency_buy.upper()
        if self.is_canonical_pair(sell, buy):
            return sell, buy
        return None

    @staticmethod
    def is_canonical_pair(sell: str, buy: str) -> bool:
        return sell in CANONICAL_SELL_CURRENCIES and buy in CANONICAL_BUY_CURRENCIES

    def parse_pair(self, currency: str) -> tuple[str, str] | None:
        upper = currency.upper()
        for sell in SUPPORTED_CURRENCIES:
            if not upper.startswith(sell):
                continue
            buy = upper.removeprefix(sell)
            if buy in SUPPORTED_CURRENCIES and buy != sell:
                return sell, buy
        return None

    def infer_country_from_pair(self, currency: str) -> Country:
        parsed = self.parse_pair(currency)
        if not parsed:
            raise self.unsupported_pair_error()

        _, buy = parsed
        country = COUNTRY_BY_BUY_CURRENCY.get(buy)
        if country is None:
            raise self.unsupported_pair_error()
        return country

    @staticmethod
    def unsupported_pair_error() -> AntExException:
        return AntExException(
            "Unsupported currency pair",
            code="UNSUPPORTED_PAIR",
            status_code=422,
        )

    @staticmethod
    def rate_unavailable_error() -> AntExException:
        return AntExException(
            "Rate is unavailable",
            code="RATE_UNAVAILABLE",
            status_code=503,
        )
