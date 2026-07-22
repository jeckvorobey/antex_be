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


async def test_upsert_many_keeps_internal_metadata_and_margin(db_session) -> None:
    """Внутренний курс обновляет цену, но сохраняет настроенную маржу."""
    repo = RateRepository(db_session)
    existing = await repo.create(
        currency="USDTRUB",
        price=90.0,
        margin=4.5,
        country=None,
        is_internal=True,
    )

    updated = await repo.upsert_many({"USDTRUB": (91.2, None, True)})

    assert updated[0].id == existing.id
    assert updated[0].price == pytest.approx(91.2)
    assert updated[0].margin == pytest.approx(4.5)
    assert updated[0].country is None
    assert updated[0].is_internal is True


async def test_visible_queries_exclude_internal_rates(db_session) -> None:
    """Внешняя выборка и поиск по id не раскрывают внутренние строки."""
    repo = RateRepository(db_session)
    visible = await repo.create(
        currency="USDTTHB",
        price=36.2,
        country=Country.THAILAND,
    )
    internal = await repo.create(
        currency="USDTRUB",
        price=91.2,
        country=None,
        is_internal=True,
    )

    assert await repo.get_visible() == [visible]
    assert await repo.get_visible_by_id(visible.id) is visible
    assert await repo.get_visible_by_id(internal.id) is None


async def test_admin_list_includes_internal_rates(db_session) -> None:
    """Административная выборка возвращает внешние и внутренние строки."""
    repo = RateRepository(db_session)
    visible = await repo.create(
        currency="USDTTHB",
        price=36.2,
        country=Country.THAILAND,
    )
    internal = await repo.create(
        currency="USDTRUB",
        price=91.2,
        country=None,
        is_internal=True,
    )

    assert await repo.get_admin_list() == [visible, internal]


async def test_has_all_currencies_requires_complete_set(db_session) -> None:
    """Проверка полноты различает частичный и полный набор пар."""
    repo = RateRepository(db_session)
    await repo.create(currency="USDTTHB", price=36.2, country=Country.THAILAND)

    assert await repo.has_all_currencies({"USDTTHB"}) is True
    assert await repo.has_all_currencies({"USDTTHB", "USDTRUB"}) is False


async def test_legacy_currency_lookup_and_upsert_are_case_insensitive(db_session) -> None:
    """Legacy-код в нижнем регистре обновляется без создания uppercase-дубликата."""
    repo = RateRepository(db_session)
    legacy = await repo.create(
        currency="usdtthb",
        price=35.0,
        margin=4.5,
        country=Country.THAILAND,
    )

    assert await repo.has_all_currencies({"USDTTHB"}) is True

    updated = await repo.upsert_many({"USDTTHB": (36.2, Country.THAILAND, False)})

    assert updated[0].id == legacy.id
    assert updated[0].currency == "USDTTHB"
    assert updated[0].price == pytest.approx(36.2)
    assert updated[0].margin == pytest.approx(4.5)
    assert len(await repo.get_all()) == 1
