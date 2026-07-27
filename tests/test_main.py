from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

from app.enums.country import Country
from app.models.rate import Rate

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.mark.asyncio
async def test_initialize_rates_if_needed_fetches_when_db_is_empty(db_session) -> None:
    from app.main import _initialize_rates_if_needed

    fetch_mock = AsyncMock(return_value={"USDTTHB": 36.0})

    initialized = await _initialize_rates_if_needed(db_session, fetch_rates=fetch_mock)

    assert initialized is True
    fetch_mock.assert_awaited_once_with(db_session)


@pytest.mark.asyncio
async def test_initialize_rates_if_needed_skips_when_rates_already_exist(db_session) -> None:
    from app.main import _initialize_rates_if_needed

    rates = [
        Rate(currency="USDTTHB", price=36.0, country=Country.THAILAND),
        Rate(currency="USDTGEL", price=2.8, country=Country.GEORGIA),
        Rate(currency="USDTVND", price=25000.0, country=Country.VIETNAM),
        Rate(currency="RUBTHB", price=0.4, country=Country.THAILAND),
        Rate(currency="RUBGEL", price=0.03, country=Country.GEORGIA),
        Rate(currency="RUBVND", price=277.0, country=Country.VIETNAM),
        Rate(currency="USDTRUB", price=90.0, country=None, is_internal=True),
        Rate(currency="RUBUSDT", price=1 / 90.0, country=None, is_internal=True),
    ]
    db_session.add_all(rates)
    await db_session.commit()

    fetch_mock = AsyncMock()

    initialized = await _initialize_rates_if_needed(db_session, fetch_rates=fetch_mock)

    assert initialized is False
    fetch_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_initialize_rates_if_needed_fetches_when_required_pairs_are_missing(
    db_session,
) -> None:
    """Непустая БД всё равно обновляется, если обязательный набор неполон."""
    from app.main import _initialize_rates_if_needed

    db_session.add(Rate(currency="USDTTHB", price=36.0, margin=3.0, country=Country.THAILAND))
    await db_session.commit()

    fetch_mock = AsyncMock(return_value={"USDTRUB": 90.0, "RUBUSDT": 1 / 90.0})

    initialized = await _initialize_rates_if_needed(db_session, fetch_rates=fetch_mock)

    assert initialized is True
    fetch_mock.assert_awaited_once_with(db_session)
