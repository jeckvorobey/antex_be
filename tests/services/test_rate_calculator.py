"""TDD тесты для rate_calculator — чистая математика, нет I/O."""
from __future__ import annotations

import pytest

from app.services.rate_calculator import build_rates, calculate_rate_with_allowance, calculate_rubthb


class TestCalculateRubthb:
    def test_basic_cross_rate(self) -> None:
        # 1 USDT = 35.5 THB, 1 USDT = 91.2 RUB → 1 RUB = 35.5/91.2 THB
        result = calculate_rubthb(usdt_thb=35.5, usdt_rub=91.2)
        assert result == pytest.approx(35.5 / 91.2, rel=1e-6)

    def test_real_world_values(self) -> None:
        # Приближённые рыночные значения апрель 2026
        result = calculate_rubthb(usdt_thb=34.0, usdt_rub=85.0)
        assert result == pytest.approx(0.4, rel=1e-6)


class TestCalculateRateWithAllowance:
    def test_two_percent_allowance_reduces_rate(self) -> None:
        # allowance=2.0% → rate * (1 - 0.02)
        result = calculate_rate_with_allowance(base_rate=0.03, allowance_pct=2.0)
        assert result == pytest.approx(0.03 * 0.98, rel=1e-6)

    def test_zero_allowance_returns_unchanged_rate(self) -> None:
        assert calculate_rate_with_allowance(base_rate=0.03, allowance_pct=0.0) == pytest.approx(0.03)

    def test_half_percent_allowance(self) -> None:
        result = calculate_rate_with_allowance(base_rate=35.5, allowance_pct=0.5)
        assert result == pytest.approx(35.5 * 0.995, rel=1e-6)

    def test_large_allowance(self) -> None:
        result = calculate_rate_with_allowance(base_rate=100.0, allowance_pct=10.0)
        assert result == pytest.approx(90.0, rel=1e-6)


class TestBuildRates:
    def test_returns_both_currency_keys(self) -> None:
        rates = build_rates(usdt_thb=35.5, usdt_rub=91.2, allowance_pct=2.0)
        assert "USDTTHB" in rates
        assert "RUBTHB" in rates

    def test_usdtthb_has_allowance_applied(self) -> None:
        rates = build_rates(usdt_thb=35.5, usdt_rub=91.2, allowance_pct=2.0)
        assert rates["USDTTHB"] == pytest.approx(35.5 * 0.98, rel=1e-6)

    def test_rubthb_is_cross_rate_with_allowance(self) -> None:
        rates = build_rates(usdt_thb=35.5, usdt_rub=91.2, allowance_pct=2.0)
        expected_rubthb = (35.5 / 91.2) * 0.98
        assert rates["RUBTHB"] == pytest.approx(expected_rubthb, rel=1e-6)

    def test_zero_allowance_gives_market_rates(self) -> None:
        rates = build_rates(usdt_thb=35.5, usdt_rub=91.2, allowance_pct=0.0)
        assert rates["USDTTHB"] == pytest.approx(35.5)
        assert rates["RUBTHB"] == pytest.approx(35.5 / 91.2, rel=1e-6)
