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

    db_session.add(Rate(currency="USDTTHB", price=36.0, margin=3.0, country=Country.THAILAND))
    await db_session.commit()

    fetch_mock = AsyncMock()

    initialized = await _initialize_rates_if_needed(db_session, fetch_rates=fetch_mock)

    assert initialized is False
    fetch_mock.assert_not_awaited()
