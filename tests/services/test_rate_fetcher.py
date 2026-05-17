"""TDD тесты для CurrencyBeacon rate_fetcher — I/O мокируется."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.services.rate_fetcher import fetch_and_save_rates, fetch_raw_rates

MOCK_CURRENCYBEACON_RESPONSE = {
    "meta": {"code": 200, "disclaimer": "mock"},
    "response": {
        "date": "2026-05-17",
        "base": "USD",
        "rates": {
            "USDT": 1.0,
            "RUB": 90.0,
            "THB": 36.0,
            "GEL": 2.8,
            "VND": 25000.0,
        },
    },
}


@pytest.fixture
def currencybeacon_settings(request: pytest.FixtureRequest) -> None:
    """Подготавливает настройки провайдера для тестов CurrencyBeacon."""
    original_values = {
        "currencybeacon_api_key": getattr(settings, "currencybeacon_api_key", None),
    }

    object.__setattr__(settings, "currencybeacon_api_key", "test-api-key")

    for field_name, value in original_values.items():
        request.addfinalizer(
            lambda name=field_name, old=value: object.__setattr__(settings, name, old)
        )


@pytest.fixture
def mock_currencybeacon(currencybeacon_settings: None) -> AsyncMock:
    """Мок HTTP-запроса к CurrencyBeacon."""
    response = MagicMock()
    response.json.return_value = MOCK_CURRENCYBEACON_RESPONSE
    response.raise_for_status.return_value = None

    with patch(
        "app.services.rate_fetcher.httpx.AsyncClient.get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = response
        yield mock_get


class TestFetchRawRates:
    async def test_returns_expected_usd_based_keys(self, mock_currencybeacon: AsyncMock) -> None:
        raw = await fetch_raw_rates()

        assert raw == {
            "usd_usdt": pytest.approx(1.0),
            "usd_rub": pytest.approx(90.0),
            "usd_thb": pytest.approx(36.0),
            "usd_gel": pytest.approx(2.8),
            "usd_vnd": pytest.approx(25000.0),
        }

    async def test_calls_currencybeacon_latest_endpoint(
        self,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        await fetch_raw_rates()

        mock_currencybeacon.assert_awaited_once_with(
            "/latest",
            params={
                "api_key": "test-api-key",
                "base": "USD",
                "symbols": "USDT,RUB,THB,GEL,VND",
            },
        )

    async def test_raises_when_api_key_missing(self) -> None:
        original_api_key = getattr(settings, "currencybeacon_api_key", None)
        object.__setattr__(settings, "currencybeacon_api_key", None)
        try:
            with pytest.raises(ValueError, match="CURRENCYBEACON_API_KEY"):
                await fetch_raw_rates()
        finally:
            object.__setattr__(settings, "currencybeacon_api_key", original_api_key)

    async def test_raises_when_response_missing_currency(
        self,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        mock_currencybeacon.return_value.json.return_value = {
            "meta": {"code": 200},
            "response": {
                "base": "USD",
                "rates": {
                    "USDT": 1.0,
                    "RUB": 90.0,
                    "THB": 36.0,
                    "GEL": 2.8,
                },
            },
        }

        with pytest.raises(ValueError, match="VND"):
            await fetch_raw_rates()

    async def test_raises_when_api_returns_error(self, mock_currencybeacon: AsyncMock) -> None:
        mock_currencybeacon.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad request",
            request=httpx.Request("GET", "https://api.currencybeacon.com/v1/latest"),
            response=httpx.Response(400),
        )

        with pytest.raises(RuntimeError, match="CurrencyBeacon"):
            await fetch_raw_rates()

    async def test_raises_when_rate_is_zero(self, mock_currencybeacon: AsyncMock) -> None:
        mock_currencybeacon.return_value.json.return_value = {
            "meta": {"code": 200},
            "response": {
                "base": "USD",
                "rates": {
                    "USDT": 0.0,
                    "RUB": 90.0,
                    "THB": 36.0,
                    "GEL": 2.8,
                    "VND": 25000.0,
                },
            },
        }

        with pytest.raises(ValueError, match="USDT"):
            await fetch_raw_rates()

    async def test_raises_when_network_fails(self, mock_currencybeacon: AsyncMock) -> None:
        mock_currencybeacon.side_effect = httpx.ReadTimeout("timeout")

        with pytest.raises(RuntimeError, match="CurrencyBeacon"):
            await fetch_raw_rates()


class TestFetchAndSaveRates:
    async def test_upserts_all_supported_currencies(
        self,
        db_session,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        from app.repositories.rate import RateRepository

        rates = await fetch_and_save_rates(db_session)

        assert set(rates) == {"USDTTHB", "USDTGEL", "USDTVND", "RUBTHB", "RUBGEL", "RUBVND"}

        repo = RateRepository(db_session)
        all_rates = await repo.get_all()
        currencies = {r.currency for r in all_rates}
        assert {"USDTTHB", "USDTGEL", "USDTVND", "RUBTHB", "RUBGEL", "RUBVND"} <= currencies

    async def test_calculates_all_six_pairs_from_usd_rates(
        self,
        db_session,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        rates = await fetch_and_save_rates(db_session)

        assert rates["USDTTHB"] == pytest.approx(36.0 / 1.0, rel=1e-6)
        assert rates["USDTGEL"] == pytest.approx(2.8 / 1.0, rel=1e-6)
        assert rates["USDTVND"] == pytest.approx(25000.0 / 1.0, rel=1e-6)
        assert rates["RUBTHB"] == pytest.approx(36.0 / 90.0, rel=1e-6)
        assert rates["RUBGEL"] == pytest.approx(2.8 / 90.0, rel=1e-6)
        assert rates["RUBVND"] == pytest.approx(25000.0 / 90.0, rel=1e-6)

    async def test_saved_rates_keep_market_price_and_default_margin(
        self,
        db_session,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        from app.repositories.rate import RateRepository

        await fetch_and_save_rates(db_session)

        repo = RateRepository(db_session)
        all_rates = {r.currency: r for r in await repo.get_all()}

        assert all_rates["USDTTHB"].price == pytest.approx(36.0, rel=1e-4)
        assert all_rates["USDTGEL"].price == pytest.approx(2.8, rel=1e-4)
        assert all_rates["RUBVND"].price == pytest.approx(25000.0 / 90.0, rel=1e-4)
        assert all_rates["USDTTHB"].margin == pytest.approx(3.0)
        assert all_rates["RUBVND"].margin == pytest.approx(3.0)

    async def test_idempotent_double_call(self, db_session, mock_currencybeacon: AsyncMock) -> None:
        from app.repositories.rate import RateRepository

        await fetch_and_save_rates(db_session)
        await fetch_and_save_rates(db_session)

        repo = RateRepository(db_session)
        all_rates = await repo.get_all()
        currencies = [r.currency for r in all_rates]
        assert len(currencies) == len(set(currencies))
