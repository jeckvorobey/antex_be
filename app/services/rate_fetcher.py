# ruff: noqa: RUF002
"""Получение курсов из CoinGecko API и сохранение в БД.

Ответственность: только I/O — HTTP запросы и запись в базу.
Математика вынесена в rate_calculator.py.
"""

from __future__ import annotations

import asyncio
import logging

from pycoingecko import CoinGeckoAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.allowance import AllowanceRepository
from app.repositories.rate import RateRepository
from app.services.rate_calculator import build_rates

logger = logging.getLogger(__name__)
TARGET_CURRENCIES = ("THB", "GEL", "VND")
COINGECKO_VS_CURRENCIES = "thb,rub,gel,vnd"


async def fetch_raw_rates() -> dict[str, float]:
    """Запрашивает у CoinGecko текущие цены USDT в поддерживаемых валютах.

    SDK синхронный — запускается в executor, чтобы не блокировать event loop.

    Returns:
        {"usdt_thb": float, "usdt_rub": float, "usdt_gel": float, "usdt_vnd": float}
    """

    def _sync() -> dict:
        cg = CoinGeckoAPI(api_key=settings.coingecko_api_key)
        return cg.get_price(ids="tether", vs_currencies=COINGECKO_VS_CURRENCIES)

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _sync)

    tether = data["tether"]
    return {f"usdt_{currency}": tether[currency] for currency in COINGECKO_VS_CURRENCIES.split(",")}


async def fetch_and_save_rates(db: AsyncSession) -> dict[str, float]:
    """Оркестратор: получает курсы → считает с надбавкой → сохраняет в БД.

    Args:
        db: активная AsyncSession.

    Returns:
        Словарь сохранённых курсов для USDT/RUB к THB/GEL/VND.
    """
    allowance_pct = await AllowanceRepository(db).get_value()
    logger.debug("Надбавка: %.2f%%", allowance_pct)

    raw = await fetch_raw_rates()
    logger.debug(
        "Сырые данные CoinGecko: usdt_thb=%.4f usdt_rub=%.4f usdt_gel=%.4f usdt_vnd=%.4f",
        raw["usdt_thb"],
        raw["usdt_rub"],
        raw["usdt_gel"],
        raw["usdt_vnd"],
    )

    rates = build_rates(
        {
            currency: raw[f"usdt_{currency.lower()}"]
            for currency in TARGET_CURRENCIES
        },
        raw["usdt_rub"],
        allowance_pct,
    )
    logger.info("Сохраняем курсы в БД: %s", rates)

    repo = RateRepository(db)
    for currency, price in rates.items():
        await repo.upsert(currency, price)

    await db.commit()
    return rates
