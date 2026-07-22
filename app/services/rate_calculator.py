# ruff: noqa: RUF002
"""Расчёт курсов валют и пользовательских значений.

Все функции — чистые (pure functions), без I/O и зависимостей.
"""

from __future__ import annotations


def calculate_cross_rate(source_rate: float, target_rate: float) -> float:
    """Считает кросс-курс source -> target через общий базовый источник.

    Формула: target / source.
    Пример для USD-базовых данных:
    - если 1 USD = 90 RUB
    - и 1 USD = 36 THB
    - то 1 RUB = 36 / 90 THB
    """
    return target_rate / source_rate


def calculate_rub_cross_rate(usdt_target: float, usdt_rub: float) -> float:
    """Кросс-курс RUB→целевой валюте через USDT как базовую валюту.

    Если 1 USDT = X целевой валюты и 1 USDT = Y RUB,
    то 1 RUB = X/Y целевой валюты.
    """
    return calculate_cross_rate(usdt_rub, usdt_target)


def apply_margin_to_rate(base_rate: float, margin_pct: float) -> float:
    """Применяет наценку обменника к рыночному курсу.

    Args:
        base_rate: рыночный курс.
        margin_pct: наценка в процентах (3.0 = 3%).

    Returns:
        base_rate * (1 - margin_pct / 100).
        При 3% клиент получает на 3% меньше целевой валюты.
    """
    return base_rate * (1 - margin_pct / 100)


def build_market_rates(
    usdt_targets: dict[str, float],
    usdt_rub: float,
) -> dict[str, float]:
    """Строит рыночные курсы для сохранения в БД.

    Returns:
        Пары USDTXXX и RUBXXX для переданных целевых валют, а также внутренние
        USDTRUB и RUBUSDT без применения наценки.
    """
    rates: dict[str, float] = {}
    for target_currency, usdt_target_rate in usdt_targets.items():
        currency = target_currency.upper()
        rates[f"USDT{currency}"] = usdt_target_rate
        rates[f"RUB{currency}"] = calculate_rub_cross_rate(usdt_target_rate, usdt_rub)

    # Внутренние пары сохраняются как взаимно обратные рыночные значения.
    rates["USDTRUB"] = usdt_rub
    rates["RUBUSDT"] = calculate_cross_rate(usdt_rub, 1.0)

    return rates
