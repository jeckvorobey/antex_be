#!/usr/bin/env python
# ruff: noqa: RUF001,RUF002
"""Ручная проверка получения курсов из CurrencyBeacon API.

Запуск из папки back/:
    python scripts/check_rates.py
    python scripts/check_rates.py --margin 3.5

Выводит в лог:
  - raw USD-базовые курсы от провайдеров
  - рассчитанный RUBTHB (кросс-курс через USDT)
  - базовые и пользовательские курсы с применённой наценкой
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

# Добавляем корень проекта в PATH, чтобы импорты работали
sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("check_rates")


async def main(margin_pct: float) -> None:
    from app.services.rate_calculator import (
        apply_margin_to_rate,
        build_market_rates,
        calculate_cross_rate,
        calculate_rub_cross_rate,
    )
    from app.services.rate_fetcher import fetch_raw_rates

    logger.info("=== AntEx Rate Check ===")
    logger.info("Наценка по умолчанию: %.2f%%", margin_pct)

    logger.info("Запрашиваем курсы у CurrencyBeacon...")
    raw = await fetch_raw_rates()

    logger.info("--- Raw данные от провайдеров ---")
    logger.info("  USD/USDT (рыночный): %.6f", raw["usd_usdt"])
    logger.info("  USD/THB  (рыночный): %.6f", raw["usd_thb"])
    if "usd_rub" not in raw:
        logger.warning("  USD/RUB  недоступен: RUB-пары не будут пересчитаны")
        return
    logger.info("  USD/RUB  (рыночный): %.6f", raw["usd_rub"])

    usdt_thb_market = calculate_cross_rate(raw["usd_usdt"], raw["usd_thb"])
    usdt_rub_market = calculate_cross_rate(raw["usd_usdt"], raw["usd_rub"])
    rubthb_market = calculate_rub_cross_rate(usdt_thb_market, usdt_rub_market)
    logger.info("  USDT/THB (рыночный, кросс): %.6f", usdt_thb_market)
    logger.info("  RUB/THB  (рыночный, кросс): %.8f", rubthb_market)

    rates = build_market_rates({"THB": usdt_thb_market}, usdt_rub_market)
    logger.info("--- Базовые курсы для сохранения в БД ---")
    logger.info("  USDTTHB: %.6f", rates["USDTTHB"])
    logger.info("  RUBTHB:  %.8f", rates["RUBTHB"])
    logger.info("--- Пользовательские курсы при наценке %.2f%% ---", margin_pct)
    logger.info("  USDTTHB: %.6f", apply_margin_to_rate(rates["USDTTHB"], margin_pct))
    logger.info("  RUBTHB:  %.8f", apply_margin_to_rate(rates["RUBTHB"], margin_pct))
    logger.info("=== Готово ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Проверка получения курсов из CurrencyBeacon")
    parser.add_argument(
        "--margin",
        type=float,
        default=3.0,
        help="Наценка в процентах (по умолчанию 3.0)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.margin))
