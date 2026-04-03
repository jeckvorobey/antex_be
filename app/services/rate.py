# ruff: noqa: RUF002
"""Чтение актуальных курсов из БД для использования в Telegram боте."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.models.rate import Rate

logger = logging.getLogger(__name__)

_REQUIRED_CURRENCIES = ("RUBTHB", "USDTTHB")


async def get_exchange_rates(allowance: float) -> dict[str, float]:
    """Читает актуальные курсы из таблицы Rates.

    Курсы уже хранятся с применённой надбавкой (записывает rate_fetcher).
    Параметр allowance принимается для совместимости с exchange.py,
    но не используется — надбавка уже учтена при записи.

    Returns:
        {"RUBTHB": float, "USDTTHB": float}
        При отсутствии данных в БД — нули.
    """
    from app.core.database import async_session

    async with async_session() as db:
        result = await db.execute(
            select(Rate).where(Rate.currency.in_(_REQUIRED_CURRENCIES))
        )
        rates_in_db = {r.currency: r.price for r in result.scalars().all()}

    if not rates_in_db:
        logger.warning("Курсы не найдены в БД, возвращаем нули")
        return dict.fromkeys(_REQUIRED_CURRENCIES, 0.0)

    return {currency: rates_in_db.get(currency, 0.0) for currency in _REQUIRED_CURRENCIES}
