# ruff: noqa: RUF002
"""Расчёт курсов валют с применением надбавки.

Все функции — чистые (pure functions), без I/O и зависимостей.
"""

from __future__ import annotations


def calculate_rubthb(usdt_thb: float, usdt_rub: float) -> float:
    """Кросс-курс RUB→THB через USDT как базовую валюту.

    Если 1 USDT = X THB и 1 USDT = Y RUB → 1 RUB = X/Y THB.
    """
    return usdt_thb / usdt_rub


def calculate_rate_with_allowance(base_rate: float, allowance_pct: float) -> float:
    """Применяет надбавку обменника к рыночному курсу.

    Args:
        base_rate: рыночный курс.
        allowance_pct: надбавка в процентах (2.0 = 2%).

    Returns:
        base_rate * (1 - allowance_pct/100).
        При 2% клиент получает на 2% меньше целевой валюты.
    """
    return base_rate * (1 - allowance_pct / 100)


def build_rates(
    usdt_thb: float,
    usdt_rub: float,
    allowance_pct: float,
) -> dict[str, float]:
    """Строит итоговые курсы с надбавкой для сохранения в БД.

    Returns:
        {"USDTTHB": float, "RUBTHB": float}
    """
    rubthb_market = calculate_rubthb(usdt_thb, usdt_rub)
    return {
        "USDTTHB": calculate_rate_with_allowance(usdt_thb, allowance_pct),
        "RUBTHB": calculate_rate_with_allowance(rubthb_market, allowance_pct),
    }
