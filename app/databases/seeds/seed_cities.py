"""Создание дефолтных городов выдачи."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.country import Country
from app.models.city import City

logger = logging.getLogger(__name__)

DEFAULT_CITIES: tuple[tuple[str, Country], ...] = (
    ("Паттайя", Country.THAILAND),
    ("Батуми", Country.GEORGIA),
    ("Начанг", Country.VIETNAM),
    ("Дананг", Country.VIETNAM),
    ("Фукуок", Country.VIETNAM),
)


async def seed_cities(db: AsyncSession) -> None:
    existing_pairs = {
        (city.name, city.country) for city in (await db.execute(select(City))).scalars()
    }

    created = 0
    for name, country in DEFAULT_CITIES:
        if (name, country) in existing_pairs:
            continue

        db.add(City(name=name, country=country))
        created += 1

    if created:
        await db.flush()
        logger.info("Created %s default cities", created)
