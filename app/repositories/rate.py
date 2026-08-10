"""Репозиторий курсов валют."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import delete, func, select

from app.enums.country import Country
from app.models.rate import Rate
from app.repositories.base import BaseRepository

DEFAULT_REVERSED_DISPLAY_CURRENCIES = frozenset({"RUBTHB", "RUBGEL", "RUBUSDT"})


class RateRepository(BaseRepository[Rate]):
    """Управляет хранением и безопасными выборками валютных курсов."""

    model = Rate

    async def has_any(self) -> bool:
        """Проверяет, есть ли в БД хотя бы один курс."""
        result = await self.session.execute(select(Rate.id).limit(1))
        return result.scalar_one_or_none() is not None

    async def has_all_currencies(self, currencies: set[str] | frozenset[str]) -> bool:
        """Проверяет наличие полного набора валютных пар в таблице."""
        normalized = {currency.upper() for currency in currencies}
        if not normalized:
            return True
        result = await self.session.execute(
            select(Rate.currency).where(func.upper(Rate.currency).in_(normalized))
        )
        existing = {currency.upper() for currency in result.scalars().all()}
        return existing == normalized

    async def find_by_currency(self, currency: str) -> Rate | None:
        """Ищет курс по коду валютной пары."""
        result = await self.session.execute(
            select(Rate).where(func.upper(Rate.currency) == currency.upper())
        )
        return result.scalar_one_or_none()

    async def find_internal_by_currency(self, currency: str) -> Rate | None:
        """Ищет системный курс по коду без расширения публичных выборок."""
        result = await self.session.execute(
            select(Rate).where(
                func.upper(Rate.currency) == currency.upper(),
                Rate.is_internal.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_visible(self) -> list[Rate]:
        """Возвращает только внешние курсы, разрешённые для API и UI."""
        result = await self.session.execute(
            select(Rate).where(Rate.is_internal.is_(False)).order_by(Rate.id)
        )
        return list(result.scalars().all())

    async def get_admin_list(self) -> list[Rate]:
        """Возвращает полный список курсов для административного просмотра."""
        result = await self.session.execute(select(Rate).order_by(Rate.id))
        return list(result.scalars().all())

    async def get_visible_by_id(self, rate_id: int) -> Rate | None:
        """Ищет внешний курс по id, не раскрывая внутренние строки."""
        result = await self.session.execute(
            select(Rate).where(Rate.id == rate_id, Rate.is_internal.is_(False))
        )
        return result.scalar_one_or_none()

    async def find_or_create(
        self,
        currency: str,
        price: float,
        *,
        country: Country,
        margin: float | None = None,
    ) -> tuple[Rate, bool]:
        normalized_currency = currency.upper()
        result = await self.session.execute(
            select(Rate).where(func.upper(Rate.currency) == normalized_currency)
        )
        rate = result.scalar_one_or_none()
        if rate:
            rate.currency = normalized_currency
            if rate.country != country:
                rate.country = country
            return rate, False
        payload: dict[str, float | str | Country] = {
            "currency": normalized_currency,
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
        normalized_currency = currency.upper()
        result = await self.session.execute(
            select(Rate).where(func.upper(Rate.currency) == normalized_currency)
        )
        rate = result.scalar_one_or_none()
        if rate:
            rate.currency = normalized_currency
            rate.price = price
            rate.country = country
            if margin is not None:
                rate.margin = margin
        else:
            payload: dict[str, float | str | Country] = {
                "currency": normalized_currency,
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
        rates: Mapping[str, tuple[float, Country | None, bool]],
        *,
        margin: float | None = None,
    ) -> list[Rate]:
        currencies = [currency.upper() for currency in rates]
        result = await self.session.execute(
            select(Rate).where(func.upper(Rate.currency).in_(currencies))
        )
        existing = {rate.currency.upper(): rate for rate in result.scalars().all()}

        upserted: list[Rate] = []
        for currency, (price, country, is_internal) in rates.items():
            normalized_currency = currency.upper()
            rate = existing.get(normalized_currency)
            if rate is None:
                payload: dict[str, float | str | Country | bool | None] = {
                    "currency": normalized_currency,
                    "price": price,
                    "country": country,
                    "is_internal": is_internal,
                    "display_reversed": (
                        normalized_currency in DEFAULT_REVERSED_DISPLAY_CURRENCIES
                    ),
                }
                if margin is not None:
                    payload["margin"] = margin
                rate = Rate(**payload)
                self.session.add(rate)
            else:
                rate.currency = normalized_currency
                rate.price = price
                rate.country = country
                rate.is_internal = is_internal
                if margin is not None:
                    rate.margin = margin
            upserted.append(rate)

        await self.session.flush()
        return upserted

    async def destroy_all(self) -> None:
        await self.session.execute(delete(Rate))
        await self.session.flush()
