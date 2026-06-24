"""TDD тесты для ReferralService."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AntExException
from app.models.user import User
from app.services.aex import AexService
from app.services.referral import ReferralService


@pytest.fixture
async def referrer(db_session: AsyncSession) -> User:
    user = User(telegram_id=200, username="referrer", first_name="Ref")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def referred(db_session: AsyncSession) -> User:
    user = User(telegram_id=300, username="referred", first_name="Referred")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def service() -> ReferralService:
    return ReferralService()


class TestReferralCodeGeneration:
    async def test_generates_code_for_new_user(
        self, db_session: AsyncSession, referrer: User, service: ReferralService
    ) -> None:
        code = await service.get_or_create_referral_code(db_session, referrer)

        assert code is not None
        assert len(code) == 8
        assert referrer.referral_code == code

    async def test_returns_existing_code(
        self, db_session: AsyncSession, referrer: User, service: ReferralService
    ) -> None:
        code1 = await service.get_or_create_referral_code(db_session, referrer)
        code2 = await service.get_or_create_referral_code(db_session, referrer)

        assert code1 == code2

    async def test_codes_are_unique(
        self, db_session: AsyncSession, service: ReferralService
    ) -> None:
        user1 = User(telegram_id=400, username="user1")
        user2 = User(telegram_id=500, username="user2")
        db_session.add_all([user1, user2])
        await db_session.flush()
        await db_session.refresh(user1)
        await db_session.refresh(user2)

        code1 = await service.get_or_create_referral_code(db_session, user1)
        code2 = await service.get_or_create_referral_code(db_session, user2)

        assert code1 != code2


class TestReferralBinding:
    async def test_bind_referral_success(
        self,
        db_session: AsyncSession,
        referrer: User,
        referred: User,
        service: ReferralService,
    ) -> None:
        code = await service.get_or_create_referral_code(db_session, referrer)
        result = await service.bind_referral(db_session, referred, code)

        assert result.referred_by == referrer.id

    async def test_bind_rejects_self_referral(
        self,
        db_session: AsyncSession,
        referrer: User,
        service: ReferralService,
    ) -> None:
        code = await service.get_or_create_referral_code(db_session, referrer)

        with pytest.raises(AntExException, match="Cannot refer yourself"):
            await service.bind_referral(db_session, referrer, code)

    async def test_bind_rejects_already_referred(
        self,
        db_session: AsyncSession,
        referrer: User,
        referred: User,
        service: ReferralService,
    ) -> None:
        code = await service.get_or_create_referral_code(db_session, referrer)
        await service.bind_referral(db_session, referred, code)

        with pytest.raises(AntExException, match="already has a referrer"):
            await service.bind_referral(db_session, referred, code)

    async def test_bind_rejects_invalid_code(
        self,
        db_session: AsyncSession,
        referred: User,
        service: ReferralService,
    ) -> None:
        with pytest.raises(AntExException, match="Invalid referral code"):
            await service.bind_referral(db_session, referred, "INVALID123")


class TestReferralStats:
    async def test_stats_empty_for_no_referrals(
        self,
        db_session: AsyncSession,
        referrer: User,
        service: ReferralService,
    ) -> None:
        count, earned = await service.get_referral_stats(db_session, referrer)

        assert count == 0
        assert earned == Decimal("0")

    async def test_stats_counts_referrals(
        self,
        db_session: AsyncSession,
        referrer: User,
        referred: User,
        service: ReferralService,
    ) -> None:
        code = await service.get_or_create_referral_code(db_session, referrer)
        await service.bind_referral(db_session, referred, code)

        count, earned = await service.get_referral_stats(db_session, referrer)

        assert count == 1
        assert earned == Decimal("0")

    async def test_stats_includes_referral_earnings(
        self,
        db_session: AsyncSession,
        referrer: User,
        referred: User,
        service: ReferralService,
    ) -> None:
        code = await service.get_or_create_referral_code(db_session, referrer)
        await service.bind_referral(db_session, referred, code)

        # Начислить AEX рефереру за реферала
        aex_service = AexService()
        await aex_service.credit(
            db_session,
            referrer.id,
            Decimal("50"),
            reference_type="referral",
            reference_id=str(referred.id),
            description="Referral bonus",
        )

        count, earned = await service.get_referral_stats(db_session, referrer)

        assert count == 1
        assert earned == Decimal("50")
