"""Репозиторий курсов валют."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import delete, select

from app.enums.country import Country
from app.models.rate import Rate
from app.repositories.base import BaseRepository


class RateRepository(BaseRepository[Rate]):
    model = Rate

    async def has_any(self) -> bool:
        """Проверяет, есть ли в БД хотя бы один курс."""
        result = await self.session.execute(select(Rate.id).limit(1))
        return result.scalar_one_or_none() is not None

    async def find_by_currency(self, currency: str) -> Rate | None:
        """Ищет курс по коду валютной пары."""
        result = await self.session.execute(select(Rate).where(Rate.currency == currency.upper()))
        return result.scalar_one_or_none()

    async def find_or_create(
        self,
        currency: str,
        price: float,
        *,
        country: Country,
        margin: float | None = None,
    ) -> tuple[Rate, bool]:
        result = await self.session.execute(select(Rate).where(Rate.currency == currency))
        rate = result.scalar_one_or_none()
        if rate:
            if rate.country != country:
                rate.country = country
            return rate, False
        payload: dict[str, float | str | Country] = {
            "currency": currency,
            "price": price,
            "country": country,
        }
        if margin is not None:
            payload["margin"] = margin
        rate = Rate(**payload)
        self.session.add(rate)
        await self.session.flush()
        return rate, True

    async def upsert(
        self,
        currency: str,
        price: float,
        *,
        country: Country,
        margin: float | None = None,
    ) -> Rate:
        result = await self.session.execute(select(Rate).where(Rate.currency == currency))
        rate = result.scalar_one_or_none()
        if rate:
            rate.price = price
            rate.country = country
            if margin is not None:
                rate.margin = margin
        else:
            payload: dict[str, float | str | Country] = {
                "currency": currency,
                "price": price,
                "country": country,
            }
            if margin is not None:
                payload["margin"] = margin
            rate = Rate(**payload)
            self.session.add(rate)
        await self.session.flush()
        return rate

    async def upsert_many(
        self,
        rates: Mapping[str, tuple[float, Country]],
        *,
        margin: float | None = None,
    ) -> list[Rate]:
        currencies = [currency.upper() for currency in rates]
        result = await self.session.execute(select(Rate).where(Rate.currency.in_(currencies)))
        existing = {rate.currency.upper(): rate for rate in result.scalars().all()}

        upserted: list[Rate] = []
        for currency, (price, country) in rates.items():
            normalized_currency = currency.upper()
            rate = existing.get(normalized_currency)
            if rate is None:
                payload: dict[str, float | str | Country] = {
                    "currency": normalized_currency,
                    "price": price,
                    "country": country,
                }
                if margin is not None:
                    payload["margin"] = margin
                rate = Rate(**payload)
                self.session.add(rate)
            else:
                rate.price = price
                rate.country = country
                if margin is not None:
                    rate.margin = margin
            upserted.append(rate)

        await self.session.flush()
        return upserted

    async def destroy_all(self) -> None:
        await self.session.execute(delete(Rate))
        await self.session.flush()
