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
    def test_list_pairs_returns_base_and_final_rates(self) -> None:
        rates = [
            _make_rate("RUBTHB", 0.41, 3.0, country=Country.THAILAND),
            _make_rate("USDTTHB", 36.2, 3.0, country=Country.THAILAND),
        ]

        pairs = ExchangeService().build_pair_snapshots(rates)

        assert pairs == [
            ExchangePairSnapshot(
                pair_id="rub-thb",
                label="RUB/THB",
                currency_sell="RUB",
                currency_buy="THB",
                country=Country.THAILAND,
                base_rate=0.41,
                client_rate=0.4,
                rate_display="0.40",
                rate_text="1 RUB = 0.40 THB",
                amount_sell_example=5000,
                amount_buy_example=2000.0,
                updated_at=rates[0].updatedAt,
                available_methods=["qrcode", "cash"],
            ),
            ExchangePairSnapshot(
                pair_id="usdt-thb",
                label="USDT/THB",
                currency_sell="USDT",
                currency_buy="THB",
                country=Country.THAILAND,
                base_rate=36.2,
                client_rate=35.11,
                rate_display="35.11",
                rate_text="1 USDT = 35.11 THB",
                amount_sell_example=100,
                amount_buy_example=3511.0,
                updated_at=rates[1].updatedAt,
                available_methods=["qrcode", "cash"],
            ),
        ]

    def test_quote_supports_reverse_pair(self) -> None:
        service = ExchangeService()
        rates = [_make_rate("RUBTHB", 0.4, 0.0, country=Country.THAILAND)]

        quote = service.build_quote(
            rates,
            ExchangeQuoteInput(currency_sell="THB", currency_buy="RUB", amount_sell=410),
        )

        assert quote.currency_sell == "THB"
        assert quote.currency_buy == "RUB"
        assert quote.rate == 2.5
        assert quote.rate_display == "2.50"
        assert quote.rate_text == "1 THB = 2.50 RUB"
        assert quote.amount_buy == pytest.approx(1025.0)

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
