# ruff: noqa: RUF002
"""Расчёт курсов валют с применением надбавки.

Все функции — чистые (pure functions), без I/O и зависимостей.
"""

from __future__ import annotations


def calculate_rub_cross_rate(usdt_target: float, usdt_rub: float) -> float:
    """Кросс-курс RUB→целевой валюте через USDT как базовую валюту.

    Если 1 USDT = X целевой валюты и 1 USDT = Y RUB,
    то 1 RUB = X/Y целевой валюты.
    """
    return usdt_target / usdt_rub


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
    usdt_targets: dict[str, float],
    usdt_rub: float,
    allowance_pct: float,
) -> dict[str, float]:
    """Строит итоговые курсы с надбавкой для сохранения в БД.

    Returns:
        Пары USDTXXX и RUBXXX для всех переданных целевых валют.
    """
    rates: dict[str, float] = {}
    for target_currency, usdt_target_rate in usdt_targets.items():
        currency = target_currency.upper()
        rates[f"USDT{currency}"] = calculate_rate_with_allowance(
            usdt_target_rate,
            allowance_pct,
        )
        rates[f"RUB{currency}"] = calculate_rate_with_allowance(
            calculate_rub_cross_rate(usdt_target_rate, usdt_rub),
            allowance_pct,
        )

    return rates
