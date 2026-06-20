"""TDD тесты для rate_calculator — чистая математика, нет I/O."""

from __future__ import annotations

import pytest

from app.services.rate_calculator import (
    apply_margin_to_rate,
    build_market_rates,
    calculate_rub_cross_rate,
)


class TestCalculateRubCrossRate:
    def test_basic_cross_rate(self) -> None:
        # 1 USDT = 35.5 THB, 1 USDT = 91.2 RUB → 1 RUB = 35.5/91.2 THB
        result = calculate_rub_cross_rate(usdt_target=35.5, usdt_rub=91.2)
        assert result == pytest.approx(35.5 / 91.2, rel=1e-6)

    def test_real_world_values(self) -> None:
        # Приближённые рыночные значения апрель 2026
        result = calculate_rub_cross_rate(usdt_target=34.0, usdt_rub=85.0)
        assert result == pytest.approx(0.4, rel=1e-6)


class TestApplyMarginToRate:
    def test_two_percent_margin_reduces_rate(self) -> None:
        result = apply_margin_to_rate(base_rate=0.03, margin_pct=2.0)
        assert result == pytest.approx(0.03 * 0.98, rel=1e-6)

    def test_zero_margin_returns_unchanged_rate(self) -> None:
        assert apply_margin_to_rate(
            base_rate=0.03,
            margin_pct=0.0,
        ) == pytest.approx(0.03)

    def test_half_percent_margin(self) -> None:
        result = apply_margin_to_rate(base_rate=35.5, margin_pct=0.5)
        assert result == pytest.approx(35.5 * 0.995, rel=1e-6)

    def test_large_margin(self) -> None:
        result = apply_margin_to_rate(base_rate=100.0, margin_pct=10.0)
        assert result == pytest.approx(90.0, rel=1e-6)


class TestBuildMarketRates:
    def test_returns_all_supported_currency_keys(self) -> None:
        rates = build_market_rates(
            usdt_targets={"THB": 35.5, "GEL": 2.72, "VND": 25500.0},
            usdt_rub=91.2,
        )
        assert set(rates) == {
            "USDTTHB",
            "USDTGEL",
            "USDTVND",
            "RUBTHB",
            "RUBGEL",
            "RUBVND",
        }

    def test_usdtthb_keeps_market_price(self) -> None:
        rates = build_market_rates(
            usdt_targets={"THB": 35.5, "GEL": 2.72, "VND": 25500.0},
            usdt_rub=91.2,
        )
        assert rates["USDTTHB"] == pytest.approx(35.5, rel=1e-6)

    def test_rub_pairs_are_market_cross_rates_without_margin(self) -> None:
        rates = build_market_rates(
            usdt_targets={"THB": 35.5, "GEL": 2.72, "VND": 25500.0},
            usdt_rub=91.2,
        )
        expected_rubthb = 35.5 / 91.2
        expected_rubgel = 2.72 / 91.2
        expected_rubvnd = 25500.0 / 91.2
        assert rates["RUBTHB"] == pytest.approx(expected_rubthb, rel=1e-6)
        assert rates["RUBGEL"] == pytest.approx(expected_rubgel, rel=1e-6)
        assert rates["RUBVND"] == pytest.approx(expected_rubvnd, rel=1e-6)

    def test_new_usdt_pairs_keep_market_price(self) -> None:
        rates = build_market_rates(
            usdt_targets={"THB": 35.5, "GEL": 2.72, "VND": 25500.0},
            usdt_rub=91.2,
        )
        assert rates["USDTGEL"] == pytest.approx(2.72, rel=1e-6)
        assert rates["USDTVND"] == pytest.approx(25500.0, rel=1e-6)
