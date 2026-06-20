from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.enums.country import Country
from app.exceptions import AntExError
from app.models.rate import Rate
from app.services.exchange import (
    ExchangePairSnapshot,
    ExchangeQuoteInput,
    ExchangeService,
)


def _make_rate(
    currency: str,
    price: float,
    margin: float,
    *,
    country: Country,
    updated_at: datetime | None = None,
) -> Rate:
    stamp = updated_at or datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    return Rate(
        id=1,
        currency=currency,
        price=price,
        margin=margin,
        country=country,
        createdAt=stamp,
        updatedAt=stamp,
    )


class TestExchangeService:
    def test_list_pairs_returns_canonical_user_facing_pairs(self) -> None:
        rates = [
            _make_rate("RUBTHB", 0.41, 3.0, country=Country.THAILAND),
            _make_rate("RUBGEL", 0.03, 3.0, country=Country.GEORGIA),
            _make_rate("RUBVND", 280.0, 3.0, country=Country.VIETNAM),
            _make_rate("USDTTHB", 36.2, 3.0, country=Country.THAILAND),
        ]

        pairs = ExchangeService().build_pair_snapshots(rates)

        assert pairs[0] == ExchangePairSnapshot(
            pair_id="rub-thb",
            label="RUB/THB",
            currency_sell="RUB",
            currency_buy="THB",
            country=Country.THAILAND,
            base_rate=0.41,
            client_rate=2.51,
            calculation_rate=0.4,
            rate_display="2.51",
            rate_text="1 THB = 2.51 RUB",
            amount_sell_example=5000,
            amount_buy_example=2000.0,
            updated_at=rates[0].updatedAt,
            available_methods=["qrcode", "cash", "bank_account", "pay_services"],
        )
        assert pairs[1] == ExchangePairSnapshot(
            pair_id="rub-gel",
            label="RUB/GEL",
            currency_sell="RUB",
            currency_buy="GEL",
            country=Country.GEORGIA,
            base_rate=0.03,
            client_rate=34.36,
            calculation_rate=0.03,
            rate_display="34.36",
            rate_text="1 GEL = 34.36 RUB",
            amount_sell_example=5000,
            amount_buy_example=150.0,
            updated_at=rates[1].updatedAt,
            available_methods=["qrcode", "cash", "bank_account", "pay_services"],
        )
        assert pairs[2] == ExchangePairSnapshot(
            pair_id="rub-vnd",
            label="RUB/VND",
            currency_sell="RUB",
            currency_buy="VND",
            country=Country.VIETNAM,
            base_rate=280.0,
            client_rate=271.6,
            calculation_rate=271.6,
            rate_display="271.60",
            rate_text="1 RUB = 271.60 VND",
            amount_sell_example=5000,
            amount_buy_example=1358000.0,
            updated_at=rates[2].updatedAt,
            available_methods=["qrcode", "cash", "bank_account", "pay_services"],
        )
        assert pairs[3] == ExchangePairSnapshot(
            pair_id="usdt-thb",
            label="USDT/THB",
            currency_sell="USDT",
            currency_buy="THB",
            country=Country.THAILAND,
            base_rate=36.2,
            client_rate=35.11,
            calculation_rate=35.11,
            rate_display="35.11",
            rate_text="1 USDT = 35.11 THB",
            amount_sell_example=100,
            amount_buy_example=3511.0,
            updated_at=rates[3].updatedAt,
            available_methods=["qrcode", "cash", "bank_account", "pay_services"],
        )

    def test_quote_rejects_reverse_pair_outside_preliminary_contract(self) -> None:
        service = ExchangeService()
        rates = [_make_rate("RUBTHB", 0.4, 0.0, country=Country.THAILAND)]

        with pytest.raises(AntExError, match="Unsupported currency pair"):
            service.build_quote(
                rates,
                ExchangeQuoteInput(currency_sell="THB", currency_buy="RUB", amount_sell=410),
            )

    def test_featured_pairs_keep_admin_display_orientation(self) -> None:
        rates = [_make_rate("RUBTHB", 0.41, 3.0, country=Country.THAILAND)]

        [snapshot] = ExchangeService().build_featured_pair_snapshots(rates)

        assert snapshot.pair_id == "rub-thb"
        assert snapshot.currency_sell == "THB"
        assert snapshot.currency_buy == "RUB"
        assert snapshot.calculation_rate == 2.51
        assert snapshot.rate_display == "2.51"
        assert snapshot.rate_text == "1 THB = 2.51 RUB"

    def test_quote_rejects_pairs_outside_canonical_scope(self) -> None:
        service = ExchangeService()
        rates = [_make_rate("THBUSDT", 0.03, 0.0, country=Country.THAILAND)]

        with pytest.raises(AntExError, match="Unsupported currency pair"):
            service.build_quote(
                rates,
                ExchangeQuoteInput(currency_sell="THB", currency_buy="USDT", amount_sell=1000),
            )

    def test_quote_rejects_unsupported_pair(self) -> None:
        service = ExchangeService()
        rates = [_make_rate("RUBTHB", 0.4, 0.0, country=Country.THAILAND)]

        with pytest.raises(AntExError, match="Unsupported currency pair"):
            service.build_quote(
                rates,
                ExchangeQuoteInput(currency_sell="RUB", currency_buy="GEL", amount_sell=1000),
            )

    def test_empty_rates_raise_unavailable(self) -> None:
        service = ExchangeService()

        with pytest.raises(AntExError, match="Rate is unavailable"):
            service.build_quote(
                [],
                ExchangeQuoteInput(currency_sell="RUB", currency_buy="THB", amount_sell=1000),
            )
