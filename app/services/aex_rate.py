"""Сервис управления ставками ATXG.

Глобальная ставка + персональные ставки.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AntExException
from app.models.aex import AexPartnerRate, AexPersonalRate, AexRate
from app.repositories.aex import (
    AexPartnerRateRepository,
    AexPersonalRateRepository,
    AexRateRepository,
)

DEFAULT_ATXG_RATE = Decimal("0.002")
ATXG_RATE_QUANTIZER = Decimal("0.000001")
ATXG_PERCENT_MULTIPLIER = Decimal("100")


def normalize_aex_rate(rate: Decimal) -> Decimal:
    """Нормализовать долю ставки ATXG для хранения и ответов."""
    return rate.quantize(ATXG_RATE_QUANTIZER)


def rate_to_percent(rate: Decimal) -> Decimal:
    """Преобразовать внутреннюю долю ставки в процент для UI/admin API."""
    return (rate * ATXG_PERCENT_MULTIPLIER).quantize(ATXG_RATE_QUANTIZER)


def percent_to_rate(percent: Decimal) -> Decimal:
    """Преобразовать пользовательский процент в внутреннюю долю ставки."""
    return normalize_aex_rate(percent / ATXG_PERCENT_MULTIPLIER)


class AexRateService:
    """Доменный сервис управления ставками ATXG."""

    async def get_global_rate(self, db: AsyncSession) -> AexRate:
        """Получить текущую глобальную ставку."""
        repo = AexRateRepository(db)
        rate = await repo.get_current()
        if rate is None:
            rate = await repo.create(global_rate=DEFAULT_ATXG_RATE)
        return rate

    async def update_global_rate(
        self,
        db: AsyncSession,
        new_rate: Decimal,
    ) -> AexRate:
        """Обновить глобальную ставку."""
        if new_rate <= 0:
            raise AntExException(
                "Rate must be positive",
                code="INVALID_RATE",
                status_code=422,
            )

        repo = AexRateRepository(db)
        rate = await repo.get_current()
        if rate is not None:
            return await repo.update(rate, global_rate=normalize_aex_rate(new_rate))
        return await repo.create(global_rate=normalize_aex_rate(new_rate))

    async def get_effective_rate(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> Decimal:
        """Получить эффективную ставку для пользователя.

        Приоритет: персональная > глобальная.
        """
        personal_repo = AexPersonalRateRepository(db)
        personal = await personal_repo.get_by_user_id(user_id)
        if personal is not None:
            return personal.rate

        global_rate = await self.get_global_rate(db)
        return global_rate.global_rate

    async def set_personal_rate(
        self,
        db: AsyncSession,
        user_id: int,
        rate: Decimal,
    ) -> AexPersonalRate:
        """Установить персональную ставку для пользователя."""
        if rate <= 0:
            raise AntExException(
                "Rate must be positive",
                code="INVALID_RATE",
                status_code=422,
            )

        repo = AexPersonalRateRepository(db)
        existing = await repo.get_by_user_id(user_id)
        if existing is not None:
            return await repo.update(existing, rate=normalize_aex_rate(rate))
        return await repo.create(user_id=user_id, rate=normalize_aex_rate(rate))

    async def set_partner_rate(
        self,
        db: AsyncSession,
        user_id: int,
        rate: Decimal,
    ) -> AexPartnerRate:
        """Установить партнёрскую ставку для пользователя."""
        if rate <= 0:
            raise AntExException(
                "Rate must be positive",
                code="INVALID_RATE",
                status_code=422,
            )

        repo = AexPartnerRateRepository(db)
        existing = await repo.get_by_user_id(user_id)
        if existing is not None:
            return await repo.update(existing, rate=normalize_aex_rate(rate))
        return await repo.create(user_id=user_id, rate=normalize_aex_rate(rate))

    async def get_all_personal_rates(self, db: AsyncSession) -> list[AexPersonalRate]:
        """Получить все персональные ставки."""
        repo = AexPersonalRateRepository(db)
        rates, _ = await repo.get_all_with_users()
        return rates

    async def get_all_partner_rates(self, db: AsyncSession) -> list[AexPartnerRate]:
        """Получить все партнёрские ставки."""
        repo = AexPartnerRateRepository(db)
        rates, _ = await repo.get_all_with_users()
        return rates

    async def delete_personal_rate(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> bool:
        """Удалить персональную ставку (вернуться к глобальной)."""
        repo = AexPersonalRateRepository(db)
        existing = await repo.get_by_user_id(user_id)
        if existing is None:
            return False
        await repo.delete(existing)
        return True

    async def delete_partner_rate(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> bool:
        """Удалить партнёрскую ставку (вернуться к глобальной)."""
        repo = AexPartnerRateRepository(db)
        existing = await repo.get_by_user_id(user_id)
        if existing is None:
            return False
        await repo.delete(existing)
        return True
