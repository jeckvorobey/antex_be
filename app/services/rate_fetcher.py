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
OPTIONAL_SYMBOLS = {"RUB"}
API_BASE_URL = "https://api.currencybeacon.com/v1"
LATEST_ENDPOINT = "/latest"
FRANKFURTER_RATES_URL = "https://api.frankfurter.dev/v2/rates"
REQUEST_TIMEOUT_SECONDS = 10.0
INTERNAL_RATE_CURRENCIES = frozenset({"USDTRUB", "RUBUSDT"})
EXPECTED_RATE_CURRENCIES = frozenset(
    {
        "USDTTHB",
        "USDTGEL",
        "USDTVND",
        "RUBTHB",
        "RUBGEL",
        "RUBVND",
        *INTERNAL_RATE_CURRENCIES,
    }
)


def _require_currencybeacon_api_key() -> str:
    """Возвращает API key CurrencyBeacon или поднимает понятную ошибку."""
    api_key = settings.currencybeacon_api_key
    if not api_key:
        raise ValueError("CURRENCYBEACON_API_KEY is required for rate refresh")
    return api_key


def _extract_rates_payload(payload: dict) -> dict[str, float | int | str | None]:
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


def _extract_valid_rate(rates: dict[str, float | int | str | None], symbol: str) -> float:
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


def _extract_frankfurter_rate(payload: object, symbol: str) -> float:
    """Извлекает курс из ответа Frankfurter /v2/rates."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("Frankfurter response does not contain rates")

    first_rate = payload[0]
    if not isinstance(first_rate, dict):
        raise ValueError("Frankfurter response contains invalid rate item")

    quote = str(first_rate.get("quote", "")).upper()
    if quote != symbol.upper():
        raise ValueError(f"Frankfurter response does not contain {symbol}")

    try:
        rate = float(first_rate["rate"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Frankfurter returned invalid rate for {symbol}") from exc

    if rate <= 0:
        raise ValueError(f"Frankfurter returned non-positive rate for {symbol}")

    return rate


async def _fetch_usd_rub_from_frankfurter(client: httpx.AsyncClient) -> float:
    """Получает USD/RUB из Frankfurter как fallback для CurrencyBeacon."""
    response = await client.get(
        FRANKFURTER_RATES_URL,
        params={"base": "USD", "quotes": "RUB"},
    )
    response.raise_for_status()
    return _extract_frankfurter_rate(response.json(), "RUB")


async def fetch_raw_rates() -> dict[str, float]:
    """Запрашивает у CurrencyBeacon USD-базовые курсы по нужным валютам.

    Returns:
        USD-базовые курсы. usd_rub может отсутствовать, если провайдер вернул
        некорректный RUB и после дозапроса.
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

            rates = _extract_rates_payload(response.json())
            resolved_rates: dict[str, float] = {}
            missing_symbols: list[str] = []

            for symbol in SUPPORTED_SYMBOLS:
                try:
                    resolved_rates[symbol] = _extract_valid_rate(rates, symbol)
                except ValueError:
                    missing_symbols.append(symbol)

            if missing_symbols:
                logger.warning(
                    "CurrencyBeacon вернул неполные/некорректные данные для %s, выполняем дозапрос",
                    ",".join(missing_symbols),
                )
                retry_response = await client.get(
                    LATEST_ENDPOINT,
                    params={
                        "api_key": api_key,
                        "base": "USD",
                        "symbols": ",".join(missing_symbols),
                    },
                )
                retry_response.raise_for_status()
                retry_rates = _extract_rates_payload(retry_response.json())

                for symbol in missing_symbols:
                    try:
                        resolved_rates[symbol] = _extract_valid_rate(retry_rates, symbol)
                    except ValueError:
                        if symbol == "RUB":
                            try:
                                resolved_rates[symbol] = await _fetch_usd_rub_from_frankfurter(
                                    client
                                )
                                logger.warning(
                                    "CurrencyBeacon не вернул RUB, используем Frankfurter USD/RUB"
                                )
                                continue
                            except (ValueError, httpx.HTTPError) as exc:
                                logger.warning(
                                    "Frankfurter не вернул валидный fallback-курс для %s: %s",
                                    symbol,
                                    exc,
                                )
                        if symbol not in OPTIONAL_SYMBOLS:
                            raise
                        logger.warning(
                            "CurrencyBeacon не вернул валидный курс для %s после дозапроса, "
                            "зависимые пары будут сохранены без обновления",
                            symbol,
                        )
    except httpx.TimeoutException as exc:
        # TODO: если потребуется продуктовый fallback, читать последний сохранённый курс из БД.
        raise RuntimeError("CurrencyBeacon request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"CurrencyBeacon returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("CurrencyBeacon network error") from exc

    return {f"usd_{symbol.lower()}": rate for symbol, rate in resolved_rates.items()}


async def fetch_and_save_rates(db: AsyncSession) -> dict[str, float]:
    """Оркестратор: получает курсы → считает рыночные пары → сохраняет в БД.

    Args:
        db: активная AsyncSession.

    Returns:
        Словарь сохранённых внешних и внутренних рыночных курсов. Все
        RUB-зависимые пары не обновляются без валидного RUB.
    """
    raw = await fetch_raw_rates()
    logger.debug(
        "Сырые данные CurrencyBeacon: "
        "usd_usdt=%.4f usd_rub=%s usd_thb=%.4f usd_gel=%.4f usd_vnd=%.4f",
        raw["usd_usdt"],
        f"{raw['usd_rub']:.4f}" if "usd_rub" in raw else "missing",
        raw["usd_thb"],
        raw["usd_gel"],
        raw["usd_vnd"],
    )

    usdt_targets = {
        currency: calculate_cross_rate(raw["usd_usdt"], raw[f"usd_{currency.lower()}"])
        for currency in TARGET_CURRENCIES
    }
    if "usd_rub" in raw:
        rates = build_market_rates(
            usdt_targets,
            calculate_cross_rate(raw["usd_usdt"], raw["usd_rub"]),
        )
    else:
        rates = {f"USDT{currency}": rate for currency, rate in usdt_targets.items()}
    logger.info("Сохраняем рыночные курсы в БД: %s", rates)

    repo = RateRepository(db)
    exchange_service = ExchangeService()
    await repo.upsert_many(
        {
            currency: (
                price,
                None
                if currency in INTERNAL_RATE_CURRENCIES
                else exchange_service.infer_country_from_pair(currency),
                currency in INTERNAL_RATE_CURRENCIES,
            )
            for currency, price in rates.items()
        }
    )

    await db.commit()
    return rates
