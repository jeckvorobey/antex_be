from __future__ import annotations

from sqlalchemy import select

from app.databases.seeds.seed_cities import DEFAULT_CITIES, seed_cities
from app.models.city import City


async def test_seed_cities_creates_default_cash_locations(db_session) -> None:
    await seed_cities(db_session)

    cities = (await db_session.execute(select(City))).scalars().all()
    actual_pairs = {(city.name, city.country) for city in cities}

    assert actual_pairs >= set(DEFAULT_CITIES)


async def test_seed_cities_is_idempotent(db_session) -> None:
    await seed_cities(db_session)
    await seed_cities(db_session)

    cities = (await db_session.execute(select(City))).scalars().all()
    actual_pairs = [(city.name, city.country) for city in cities]

    assert len(actual_pairs) == len(set(actual_pairs))
