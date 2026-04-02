"""Репозиторий городов."""

from __future__ import annotations

from sqlalchemy import select

from app.models.city import City
from app.repositories.base import BaseRepository


class CityRepository(BaseRepository[City]):
    model = City

    async def get_by_name(self, name: str) -> City | None:
        result = await self.session.execute(select(City).where(City.name == name))
        return result.scalar_one_or_none()
