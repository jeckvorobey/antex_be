"""TDD тесты для rate_fetcher — I/O мокируется."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.rate_fetcher import fetch_and_save_rates, fetch_raw_rates

MOCK_COINGECKO_RESPONSE = {"tether": {"thb": 35.5, "rub": 91.2}}


@pytest.fixture
def mock_coingecko():
    """Мок синхронного вызова CoinGecko SDK."""
    with patch("app.services.rate_fetcher.CoinGeckoAPI") as mock_cls:
        instance = MagicMock()
        instance.get_price.return_value = MOCK_COINGECKO_RESPONSE
        mock_cls.return_value = instance
        yield instance


class TestFetchRawRates:
    async def test_returns_usdt_thb_key(self, mock_coingecko) -> None:
        raw = await fetch_raw_rates()
        assert "usdt_thb" in raw

    async def test_returns_usdt_rub_key(self, mock_coingecko) -> None:
        raw = await fetch_raw_rates()
        assert "usdt_rub" in raw

    async def test_correct_values_from_api(self, mock_coingecko) -> None:
        raw = await fetch_raw_rates()
        assert raw["usdt_thb"] == pytest.approx(35.5)
        assert raw["usdt_rub"] == pytest.approx(91.2)

    async def test_calls_coingecko_get_price(self, mock_coingecko) -> None:
        await fetch_raw_rates()
        mock_coingecko.get_price.assert_called_once_with(ids="tether", vs_currencies="thb,rub")


class TestFetchAndSaveRates:
    async def test_upserts_both_currencies(self, db_session, mock_coingecko) -> None:
        from app.repositories.rate import RateRepository

        rates = await fetch_and_save_rates(db_session)

        assert "USDTTHB" in rates
        assert "RUBTHB" in rates

        repo = RateRepository(db_session)
        all_rates = await repo.get_all()
        currencies = {r.currency for r in all_rates}
        assert "USDTTHB" in currencies
        assert "RUBTHB" in currencies

    async def test_saved_rates_have_allowance_applied(self, db_session, mock_coingecko) -> None:
        from app.repositories.config import ConfigRepository
        from app.repositories.rate import RateRepository

        # Устанавливаем надбавку 2%
        await ConfigRepository(db_session).set_allowance(2.0)
        await db_session.flush()

        await fetch_and_save_rates(db_session)

        repo = RateRepository(db_session)
        all_rates = {r.currency: r.price for r in await repo.get_all()}

        # USDTTHB = 35.5 * 0.98
        assert all_rates["USDTTHB"] == pytest.approx(35.5 * 0.98, rel=1e-4)

    async def test_idempotent_double_call(self, db_session, mock_coingecko) -> None:
        from app.repositories.rate import RateRepository

        await fetch_and_save_rates(db_session)
        await fetch_and_save_rates(db_session)

        repo = RateRepository(db_session)
        all_rates = await repo.get_all()
        # Не должно быть дублей — upsert
        currencies = [r.currency for r in all_rates]
        assert len(currencies) == len(set(currencies))
