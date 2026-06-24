"""TDD тесты для AexRateService."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AntExException
from app.models.user import User
from app.services.aex_rate import AexRateService


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    user = User(telegram_id=600, username="rate_user", first_name="Rate")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def service() -> AexRateService:
    return AexRateService()


class TestGlobalRate:
    async def test_get_global_rate_creates_default(
        self, db_session: AsyncSession, service: AexRateService
    ) -> None:
        rate = await service.get_global_rate(db_session)

        assert rate.global_rate == Decimal("0.002")
        assert rate.id is not None

    async def test_get_global_rate_returns_existing(
        self, db_session: AsyncSession, service: AexRateService
    ) -> None:
        rate1 = await service.get_global_rate(db_session)
        rate2 = await service.get_global_rate(db_session)

        assert rate1.id == rate2.id

    async def test_update_global_rate(
        self, db_session: AsyncSession, service: AexRateService
    ) -> None:
        await service.get_global_rate(db_session)
        updated = await service.update_global_rate(db_session, Decimal("0.005"))

        assert updated.global_rate == Decimal("0.005")

    async def test_update_global_rate_rejects_zero(
        self, db_session: AsyncSession, service: AexRateService
    ) -> None:
        with pytest.raises(AntExException, match="Rate must be positive"):
            await service.update_global_rate(db_session, Decimal("0"))

    async def test_update_global_rate_rejects_negative(
        self, db_session: AsyncSession, service: AexRateService
    ) -> None:
        with pytest.raises(AntExException, match="Rate must be positive"):
            await service.update_global_rate(db_session, Decimal("-0.001"))


class TestEffectiveRate:
    async def test_effective_rate_defaults_to_global(
        self, db_session: AsyncSession, user: User, service: AexRateService
    ) -> None:
        rate = await service.get_effective_rate(db_session, user.id)

        assert rate == Decimal("0.002")

    async def test_effective_rate_uses_personal(
        self, db_session: AsyncSession, user: User, service: AexRateService
    ) -> None:
        await service.set_personal_rate(db_session, user.id, Decimal("0.01"))

        rate = await service.get_effective_rate(db_session, user.id)

        assert rate == Decimal("0.01")

    async def test_personal_rate_overrides_global(
        self, db_session: AsyncSession, user: User, service: AexRateService
    ) -> None:
        await service.update_global_rate(db_session, Decimal("0.003"))
        await service.set_personal_rate(db_session, user.id, Decimal("0.008"))

        rate = await service.get_effective_rate(db_session, user.id)

        assert rate == Decimal("0.008")


class TestPersonalRate:
    async def test_set_personal_rate(
        self, db_session: AsyncSession, user: User, service: AexRateService
    ) -> None:
        rate = await service.set_personal_rate(db_session, user.id, Decimal("0.005"))

        assert rate.user_id == user.id
        assert rate.rate == Decimal("0.005")

    async def test_update_existing_personal_rate(
        self, db_session: AsyncSession, user: User, service: AexRateService
    ) -> None:
        await service.set_personal_rate(db_session, user.id, Decimal("0.005"))
        updated = await service.set_personal_rate(db_session, user.id, Decimal("0.01"))

        assert updated.rate == Decimal("0.01")

    async def test_set_personal_rate_rejects_zero(
        self, db_session: AsyncSession, user: User, service: AexRateService
    ) -> None:
        with pytest.raises(AntExException, match="Rate must be positive"):
            await service.set_personal_rate(db_session, user.id, Decimal("0"))

    async def test_delete_personal_rate(
        self, db_session: AsyncSession, user: User, service: AexRateService
    ) -> None:
        await service.set_personal_rate(db_session, user.id, Decimal("0.005"))
        deleted = await service.delete_personal_rate(db_session, user.id)

        assert deleted is True

        # Should fall back to global
        rate = await service.get_effective_rate(db_session, user.id)
        assert rate == Decimal("0.002")

    async def test_delete_nonexistent_personal_rate(
        self, db_session: AsyncSession, user: User, service: AexRateService
    ) -> None:
        deleted = await service.delete_personal_rate(db_session, user.id)
        assert deleted is False

    async def test_get_all_personal_rates(
        self, db_session: AsyncSession, service: AexRateService
    ) -> None:
        user1 = User(telegram_id=700, username="pr1")
        user2 = User(telegram_id=800, username="pr2")
        db_session.add_all([user1, user2])
        await db_session.flush()
        await db_session.refresh(user1)
        await db_session.refresh(user2)

        await service.set_personal_rate(db_session, user1.id, Decimal("0.005"))
        await service.set_personal_rate(db_session, user2.id, Decimal("0.01"))

        rates = await service.get_all_personal_rates(db_session)

        assert len(rates) == 2
