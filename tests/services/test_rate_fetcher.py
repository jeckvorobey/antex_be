"""TDD тесты для CurrencyBeacon rate_fetcher — I/O мокируется."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
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


@contextmanager
def count_sql_statements(db_session: AsyncSession) -> Iterator[list[str]]:
    statements: list[str] = []
    bind = db_session.get_bind()

    def before_cursor_execute(
        conn,
        cursor,
        statement: str,
        parameters,
        context,
        executemany: bool,
    ) -> None:
        del conn, cursor, parameters, context, executemany
        statements.append(statement)

    event.listen(bind, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(bind, "before_cursor_execute", before_cursor_execute)


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
    def test_rate_refresh_ttl_defaults_to_one_day(self) -> None:
        assert Settings.model_fields["rate_cache_ttl_seconds"].default == 86400

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

    async def test_network_event_does_not_receive_api_key_or_url(
        self, mock_currencybeacon: AsyncMock
    ) -> None:
        with patch("app.services.rate_fetcher.emit_outbound_network_event") as emit:
            await fetch_raw_rates()

        emit.assert_called_once()
        event = emit.call_args.kwargs
        assert event["provider"] == "currencybeacon"
        assert event["operation"] == "latest"
        assert "test-api-key" not in repr(event)
        assert "http" not in repr(event)

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

    async def test_http_error_does_not_keep_request_url_with_api_key(
        self,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        """Исключение не должно нести request URL, содержащий ключ."""
        mock_currencybeacon.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad request",
            request=httpx.Request(
                "GET",
                "https://api.currencybeacon.com/v1/latest?api_key=test-api-key",
            ),
            response=httpx.Response(400),
        )

        with pytest.raises(RuntimeError, match="CurrencyBeacon") as error:
            await fetch_raw_rates()

        assert error.value.__cause__ is None

    @pytest.mark.parametrize(
        "request_error",
        [
            httpx.ReadTimeout(
                "timeout",
                request=httpx.Request(
                    "GET",
                    "https://api.currencybeacon.com/v1/latest?api_key=test-api-key",
                ),
            ),
            httpx.ConnectError(
                "network error",
                request=httpx.Request(
                    "GET",
                    "https://api.currencybeacon.com/v1/latest?api_key=test-api-key",
                ),
            ),
        ],
    )
    async def test_network_error_does_not_keep_request_url_with_api_key(
        self,
        mock_currencybeacon: AsyncMock,
        request_error: httpx.HTTPError,
    ) -> None:
        mock_currencybeacon.side_effect = request_error

        with pytest.raises(RuntimeError, match="CurrencyBeacon") as error:
            await fetch_raw_rates()

        assert error.value.__cause__ is None

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

    async def test_refetches_missing_or_null_symbol(self, mock_currencybeacon: AsyncMock) -> None:
        first_response = MagicMock()
        first_response.raise_for_status.return_value = None
        first_response.json.return_value = {
            "meta": {"code": 200},
            "response": {
                "base": "USD",
                "rates": {
                    "USDT": 1.0,
                    "RUB": None,
                    "THB": 36.0,
                    "GEL": 2.8,
                    "VND": 25000.0,
                },
            },
        }
        second_response = MagicMock()
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            "meta": {"code": 200},
            "response": {
                "base": "USD",
                "rates": {
                    "RUB": 90.0,
                },
            },
        }
        mock_currencybeacon.side_effect = [first_response, second_response]

        raw = await fetch_raw_rates()

        assert raw["usd_rub"] == pytest.approx(90.0)
        assert mock_currencybeacon.await_count == 2

    async def test_falls_back_to_frankfurter_when_rub_stays_null(
        self,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        first_response = MagicMock()
        first_response.raise_for_status.return_value = None
        first_response.json.return_value = {
            "meta": {"code": 200},
            "response": {
                "base": "USD",
                "rates": {
                    "USDT": 1.0,
                    "RUB": None,
                    "THB": 36.0,
                    "GEL": 2.8,
                    "VND": 25000.0,
                },
            },
        }
        second_response = MagicMock()
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            "meta": {"code": 200},
            "response": {"base": "USD", "rates": {"RUB": None}},
        }
        frankfurter_response = MagicMock()
        frankfurter_response.raise_for_status.return_value = None
        frankfurter_response.json.return_value = [
            {"date": "2026-05-30", "base": "USD", "quote": "RUB", "rate": 71.128}
        ]
        mock_currencybeacon.side_effect = [first_response, second_response, frankfurter_response]

        raw = await fetch_raw_rates()

        assert raw["usd_rub"] == pytest.approx(71.128)
        assert mock_currencybeacon.await_count == 3


class TestFetchAndSaveRates:
    async def test_upserts_all_supported_currencies(
        self,
        db_session,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        from app.repositories.rate import RateRepository

        rates = await fetch_and_save_rates(db_session)

        assert set(rates) == {
            "USDTTHB",
            "USDTGEL",
            "USDTVND",
            "USDTRUB",
            "RUBTHB",
            "RUBGEL",
            "RUBVND",
            "RUBUSDT",
        }

        repo = RateRepository(db_session)
        all_rates = await repo.get_all()
        currencies = {r.currency for r in all_rates}
        assert {
            "USDTTHB",
            "USDTGEL",
            "USDTVND",
            "USDTRUB",
            "RUBTHB",
            "RUBGEL",
            "RUBVND",
            "RUBUSDT",
        } <= currencies
        by_currency = {rate.currency: rate for rate in all_rates}
        assert by_currency["USDTRUB"].country is None
        assert by_currency["USDTRUB"].is_internal is True
        assert by_currency["RUBUSDT"].country is None
        assert by_currency["RUBUSDT"].is_internal is True

    async def test_calculates_all_eight_pairs_from_usd_rates(
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
        assert rates["USDTRUB"] == pytest.approx(90.0 / 1.0, rel=1e-6)
        assert rates["RUBUSDT"] == pytest.approx(1.0 / 90.0, rel=1e-6)

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
        assert all_rates["USDTRUB"].margin == pytest.approx(3.0)
        assert all_rates["RUBUSDT"].margin == pytest.approx(3.0)

    async def test_idempotent_double_call(self, db_session, mock_currencybeacon: AsyncMock) -> None:
        from app.repositories.rate import RateRepository

        await fetch_and_save_rates(db_session)
        await fetch_and_save_rates(db_session)

        repo = RateRepository(db_session)
        all_rates = await repo.get_all()
        currencies = [r.currency for r in all_rates]
        assert len(currencies) == len(set(currencies))

    async def test_refresh_fetches_existing_rates_in_bulk(
        self,
        db_session,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        await fetch_and_save_rates(db_session)

        with count_sql_statements(db_session) as statements:
            await fetch_and_save_rates(db_session)

        rate_selects = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith("SELECT")
            and ('FROM "RATES"' in statement.upper() or "FROM RATES" in statement.upper())
        ]
        assert len(rate_selects) == 1

    async def test_persistent_null_rub_keeps_existing_rub_rates(
        self,
        db_session,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        from app.enums.country import Country
        from app.repositories.rate import RateRepository

        repo = RateRepository(db_session)
        await repo.upsert("RUBTHB", 0.41, country=Country.THAILAND)
        await repo.create(
            currency="USDTRUB",
            price=88.0,
            margin=4.0,
            country=None,
            is_internal=True,
        )
        await repo.create(
            currency="RUBUSDT",
            price=1 / 88.0,
            margin=5.0,
            country=None,
            is_internal=True,
        )
        await db_session.commit()

        first_response = MagicMock()
        first_response.raise_for_status.return_value = None
        first_response.json.return_value = {
            "meta": {"code": 200},
            "response": {
                "base": "USD",
                "rates": {
                    "USDT": 1.0,
                    "RUB": None,
                    "THB": 36.0,
                    "GEL": 2.8,
                    "VND": 25000.0,
                },
            },
        }
        second_response = MagicMock()
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            "meta": {"code": 200},
            "response": {
                "base": "USD",
                "rates": {
                    "RUB": None,
                },
            },
        }
        frankfurter_response = MagicMock()
        frankfurter_response.raise_for_status.return_value = None
        frankfurter_response.json.return_value = []
        mock_currencybeacon.side_effect = [first_response, second_response, frankfurter_response]

        rates = await fetch_and_save_rates(db_session)

        all_rates = {r.currency: r for r in await repo.get_all()}
        assert set(rates) == {"USDTTHB", "USDTGEL", "USDTVND"}
        assert all_rates["USDTTHB"].price == pytest.approx(36.0)
        assert all_rates["RUBTHB"].price == pytest.approx(0.41)
        assert all_rates["USDTRUB"].price == pytest.approx(88.0)
        assert all_rates["USDTRUB"].margin == pytest.approx(4.0)
        assert all_rates["RUBUSDT"].price == pytest.approx(1 / 88.0)
        assert all_rates["RUBUSDT"].margin == pytest.approx(5.0)

    async def test_rub_fallback_still_upserts_all_supported_currencies(
        self,
        db_session,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        first_response = MagicMock()
        first_response.raise_for_status.return_value = None
        first_response.json.return_value = {
            "meta": {"code": 200},
            "response": {
                "base": "USD",
                "rates": {
                    "USDT": 1.0,
                    "RUB": None,
                    "THB": 36.0,
                    "GEL": 2.8,
                    "VND": 25000.0,
                },
            },
        }
        second_response = MagicMock()
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            "meta": {"code": 200},
            "response": {"base": "USD", "rates": {"RUB": None}},
        }
        frankfurter_response = MagicMock()
        frankfurter_response.raise_for_status.return_value = None
        frankfurter_response.json.return_value = [
            {"date": "2026-05-30", "base": "USD", "quote": "RUB", "rate": 90.0}
        ]
        mock_currencybeacon.side_effect = [first_response, second_response, frankfurter_response]

        rates = await fetch_and_save_rates(db_session)

        assert set(rates) == {
            "USDTTHB",
            "USDTGEL",
            "USDTVND",
            "USDTRUB",
            "RUBTHB",
            "RUBGEL",
            "RUBVND",
            "RUBUSDT",
        }
        assert rates["RUBTHB"] == pytest.approx(36.0 / 90.0, rel=1e-6)

    async def test_refresh_preserves_internal_margin(
        self,
        db_session,
        mock_currencybeacon: AsyncMock,
    ) -> None:
        """Автообновление внутренних пар не сбрасывает ручную маржу."""
        from app.repositories.rate import RateRepository

        repo = RateRepository(db_session)
        await repo.create(
            currency="USDTRUB",
            price=80.0,
            margin=4.5,
            country=None,
            is_internal=True,
        )
        await db_session.commit()

        await fetch_and_save_rates(db_session)

        updated = await repo.find_by_currency("USDTRUB")
        assert updated is not None
        assert updated.price == pytest.approx(90.0)
        assert updated.margin == pytest.approx(4.5)
