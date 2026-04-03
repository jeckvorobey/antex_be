#!/usr/bin/env python
"""Ручная проверка получения курсов из CoinGecko API.

Запуск из папки back/:
    python scripts/check_rates.py
    python scripts/check_rates.py --allowance 3.5

Выводит в лог:
  - raw курсы от CoinGecko (без надбавки)
  - рассчитанный RUBTHB (кросс-курс через USDT)
  - финальные курсы с надбавкой
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


async def main(allowance_pct: float) -> None:
    from app.services.rate_calculator import build_rates, calculate_rubthb
    from app.services.rate_fetcher import fetch_raw_rates

    logger.info("=== AntEx Rate Check ===")
    logger.info("Надбавка (allowance): %.2f%%", allowance_pct)

    logger.info("Запрашиваем курсы у CoinGecko...")
    raw = await fetch_raw_rates()

    logger.info("--- Raw данные от CoinGecko ---")
    logger.info("  USDT/THB (рыночный): %.6f", raw["usdt_thb"])
    logger.info("  USDT/RUB (рыночный): %.6f", raw["usdt_rub"])

    rubthb_market = calculate_rubthb(raw["usdt_thb"], raw["usdt_rub"])
    logger.info("  RUB/THB  (рыночный, кросс): %.8f", rubthb_market)

    rates = build_rates(raw["usdt_thb"], raw["usdt_rub"], allowance_pct)
    logger.info("--- Курсы с надбавкой %.2f%% ---", allowance_pct)
    logger.info("  USDTTHB: %.6f  (было %.6f)", rates["USDTTHB"], raw["usdt_thb"])
    logger.info("  RUBTHB:  %.8f  (было %.8f)", rates["RUBTHB"], rubthb_market)
    logger.info("=== Готово ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Проверка получения курсов из CoinGecko")
    parser.add_argument(
        "--allowance",
        type=float,
        default=2.0,
        help="Надбавка в процентах (по умолчанию 2.0)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.allowance))
