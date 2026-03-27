"""Сервис курсов валют (CoinGecko + расчёт RUBTHB)."""

from __future__ import annotations

import json
import logging

import httpx

from app.core.config import settings
from app.core.redis import redis_client

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
RATE_CACHE_KEY = "rates:current"


async def fetch_from_coingecko() -> dict[str, float]:
    """Получить курсы USDT/RUB и USDT/THB с CoinGecko."""
    params = {
        "ids": "tether",
        "vs_currencies": "rub,thb",
    }
    headers = {}
    if settings.coingecko_api_key:
        headers["x-cg-demo-api-key"] = settings.coingecko_api_key

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(COINGECKO_URL, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    usdtrub: float = data["tether"]["rub"]
    usdtthb: float = data["tether"]["thb"]
    return {"USDTRUB": usdtrub, "USDTTHB": usdtthb}


async def store_rates(rates: dict[str, float]) -> None:
    """Сохранить курсы в Redis."""
    await redis_client.setex(
        RATE_CACHE_KEY,
        settings.rate_cache_ttl_seconds,
        json.dumps(rates),
    )


async def get_cached_rates() -> dict[str, float] | None:
    raw = await redis_client.get(RATE_CACHE_KEY)
    if raw:
        return json.loads(raw)
    return None


def calc_rubthb(usdtrub: float, usdtthb: float, allowance: float) -> float:
    """Расчёт курса RUB→THB.

    thbrub = usdtthb - REDUCING_FACTOR
    rubthb = (usdtrub / thbrub) + (usdtrub / thbrub * allowance)
    """
    thbrub = usdtthb - settings.reducing_factor
    if thbrub <= 0:
        thbrub = usdtthb
    rubthb = (usdtrub / thbrub) + (usdtrub / thbrub * allowance)
    return round(rubthb, 4)


async def get_exchange_rates(allowance: float | None = None) -> dict:
    """Вернуть актуальные курсы (из кеша или CoinGecko)."""
    if allowance is None:
        allowance = settings.default_allowance

    rates = await get_cached_rates()
    if not rates:
        try:
            rates = await fetch_from_coingecko()
            await store_rates(rates)
        except Exception:
            logger.exception("CoinGecko fetch failed")
            rates = {"USDTRUB": 0.0, "USDTTHB": 0.0}

    rubthb = calc_rubthb(rates["USDTRUB"], rates["USDTTHB"], allowance)
    return {
        "USDTRUB": rates["USDTRUB"],
        "USDTTHB": rates["USDTTHB"],
        "RUBTHB": rubthb,
        "allowance": allowance,
    }
