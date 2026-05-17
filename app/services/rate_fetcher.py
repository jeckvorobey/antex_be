# ruff: noqa: RUF002
"""Получение курсов из CurrencyBeacon API и сохранение в БД.

Ответственность: только I/O — HTTP запросы и запись в базу.
Математика вынесена в rate_calculator.py.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.rate import RateRepository
from app.services.exchange import ExchangeService
from app.services.rate_calculator import build_market_rates, calculate_cross_rate

logger = logging.getLogger(__name__)
TARGET_CURRENCIES = ("THB", "GEL", "VND")
SUPPORTED_SYMBOLS = ("USDT", "RUB", "THB", "GEL", "VND")
API_BASE_URL = "https://api.currencybeacon.com/v1"
LATEST_ENDPOINT = "/latest"
REQUEST_TIMEOUT_SECONDS = 10.0


def _require_currencybeacon_api_key() -> str:
    """Возвращает API key CurrencyBeacon или поднимает понятную ошибку."""
    api_key = settings.currencybeacon_api_key
    if not api_key:
        raise ValueError("CURRENCYBEACON_API_KEY is required for rate refresh")
    return api_key


def _extract_rates_payload(payload: dict) -> dict[str, float | int | str]:
    """Достаёт блок rates и валидирует прикладной статус ответа."""
    meta = payload.get("meta")
    if isinstance(meta, dict):
        code = meta.get("code")
        if code not in (None, 200):
            raise RuntimeError(f"CurrencyBeacon API error: meta.code={code}")

    response = payload.get("response")
    if not isinstance(response, dict):
        raise ValueError("CurrencyBeacon response does not contain 'response' object")

    rates = response.get("rates")
    if not isinstance(rates, dict):
        raise ValueError("CurrencyBeacon response does not contain 'rates'")

    return rates


def _extract_valid_rate(rates: dict[str, float | int | str], symbol: str) -> float:
    """Извлекает и валидирует числовой курс для одной валюты."""
    if symbol not in rates:
        raise ValueError(f"CurrencyBeacon response is missing required currency: {symbol}")

    try:
        rate = float(rates[symbol])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"CurrencyBeacon returned invalid rate for {symbol}") from exc

    if rate <= 0:
        raise ValueError(f"CurrencyBeacon returned non-positive rate for {symbol}")

    return rate


async def fetch_raw_rates() -> dict[str, float]:
    """Запрашивает у CurrencyBeacon USD-базовые курсы по нужным валютам.

    Returns:
        {"usd_usdt": float, "usd_rub": float, "usd_thb": float, "usd_gel": float, "usd_vnd": float}
    """
    api_key = _require_currencybeacon_api_key()

    try:
        async with httpx.AsyncClient(
            base_url=API_BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = await client.get(
                LATEST_ENDPOINT,
                params={
                    "api_key": api_key,
                    "base": "USD",
                    "symbols": ",".join(SUPPORTED_SYMBOLS),
                },
            )
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        # TODO: если потребуется продуктовый fallback, читать последний сохранённый курс из БД.
        raise RuntimeError("CurrencyBeacon request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"CurrencyBeacon returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("CurrencyBeacon network error") from exc

    rates = _extract_rates_payload(response.json())
    return {
        f"usd_{symbol.lower()}": _extract_valid_rate(rates, symbol) for symbol in SUPPORTED_SYMBOLS
    }


async def fetch_and_save_rates(db: AsyncSession) -> dict[str, float]:
    """Оркестратор: получает курсы → считает рыночные пары → сохраняет в БД.

    Args:
        db: активная AsyncSession.

    Returns:
        Словарь сохранённых рыночных курсов для USDT/RUB к THB/GEL/VND.
    """
    raw = await fetch_raw_rates()
    logger.debug(
        "Сырые данные CurrencyBeacon: "
        "usd_usdt=%.4f usd_rub=%.4f usd_thb=%.4f usd_gel=%.4f usd_vnd=%.4f",
        raw["usd_usdt"],
        raw["usd_rub"],
        raw["usd_thb"],
        raw["usd_gel"],
        raw["usd_vnd"],
    )

    rates = build_market_rates(
        {
            currency: calculate_cross_rate(raw["usd_usdt"], raw[f"usd_{currency.lower()}"])
            for currency in TARGET_CURRENCIES
        },
        calculate_cross_rate(raw["usd_usdt"], raw["usd_rub"]),
    )
    logger.info("Сохраняем рыночные курсы в БД: %s", rates)

    repo = RateRepository(db)
    exchange_service = ExchangeService()
    for currency, price in rates.items():
        await repo.upsert(
            currency,
            price,
            country=exchange_service.infer_country_from_pair(currency),
        )

    await db.commit()
    return rates
