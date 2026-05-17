#!/usr/bin/env python
# ruff: noqa: RUF001,RUF002
"""Ручная проверка получения курсов из CoinGecko API.

Запуск из папки back/:
    python scripts/check_rates.py
    python scripts/check_rates.py --margin 3.5

Выводит в лог:
  - raw курсы от CoinGecko (рыночные)
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
        calculate_rub_cross_rate,
    )
    from app.services.rate_fetcher import fetch_raw_rates

    logger.info("=== AntEx Rate Check ===")
    logger.info("Наценка по умолчанию: %.2f%%", margin_pct)

    logger.info("Запрашиваем курсы у CoinGecko...")
    raw = await fetch_raw_rates()

    logger.info("--- Raw данные от CoinGecko ---")
    logger.info("  USDT/THB (рыночный): %.6f", raw["usdt_thb"])
    logger.info("  USDT/RUB (рыночный): %.6f", raw["usdt_rub"])

    rubthb_market = calculate_rub_cross_rate(raw["usdt_thb"], raw["usdt_rub"])
    logger.info("  RUB/THB  (рыночный, кросс): %.8f", rubthb_market)

    rates = build_market_rates({"THB": raw["usdt_thb"]}, raw["usdt_rub"])
    logger.info("--- Базовые курсы для сохранения в БД ---")
    logger.info("  USDTTHB: %.6f", rates["USDTTHB"])
    logger.info("  RUBTHB:  %.8f", rates["RUBTHB"])
    logger.info("--- Пользовательские курсы при наценке %.2f%% ---", margin_pct)
    logger.info("  USDTTHB: %.6f", apply_margin_to_rate(rates["USDTTHB"], margin_pct))
    logger.info("  RUBTHB:  %.8f", apply_margin_to_rate(rates["RUBTHB"], margin_pct))
    logger.info("=== Готово ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Проверка получения курсов из CoinGecko")
    parser.add_argument(
        "--margin",
        type=float,
        default=3.0,
        help="Наценка в процентах (по умолчанию 3.0)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.margin))
