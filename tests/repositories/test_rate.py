"""TDD тесты для RateRepository и дефолтной margin-модели."""

from __future__ import annotations

import pytest

from app.enums.country import Country
from app.repositories.rate import RateRepository


async def test_create_rate_sets_default_margin(db_session) -> None:
    repo = RateRepository(db_session)

    rate = await repo.create(
        currency="RUBTHB",
        price=0.41,
        country=Country.THAILAND,
    )

    assert rate.margin == pytest.approx(3.0)
    assert rate.country == Country.THAILAND


async def test_upsert_updates_price_without_resetting_existing_margin(db_session) -> None:
    repo = RateRepository(db_session)
    existing = await repo.create(
        currency="RUBTHB",
        price=0.41,
        margin=4.5,
        country=Country.THAILAND,
    )

    updated = await repo.upsert("RUBTHB", 0.5, country=Country.THAILAND)

    assert updated.id == existing.id
    assert updated.price == pytest.approx(0.5)
    assert updated.margin == pytest.approx(4.5)


async def test_upsert_creates_rate_with_default_margin_when_missing(db_session) -> None:
    repo = RateRepository(db_session)

    created = await repo.upsert("USDTTHB", 36.2, country=Country.THAILAND)

    assert created.margin == pytest.approx(3.0)
    assert created.country == Country.THAILAND
