"""TDD тесты для ReferralService."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AntExException
from app.models.user import User
from app.services.aex import AexService
from app.services.referral import ReferralService, build_referral_link


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


class TestReferralLinkBuilder:
    def test_build_referral_link_uses_configured_bot_username(self) -> None:
        assert build_referral_link("ABC12345", "@antex_test_bot") == (
            "https://t.me/antex_test_bot?startapp=ref_ABC12345"
        )

    def test_build_referral_link_falls_back_to_default_bot_username(self) -> None:
        assert build_referral_link("ABC12345", "") == (
            "https://t.me/antex_bot?startapp=ref_ABC12345"
        )


class TestReferralCodeGeneration:
    async def test_generates_code_for_new_user(
        self, db_session: AsyncSession, referrer: User, service: ReferralService
    ) -> None:
        code = await service.get_or_create_referral_code(db_session, referrer)

        assert code is not None
        assert len(code) == 8
        assert referrer.referral_code == code

    async def test_generated_code_contains_only_ascii_letters_and_digits(
        self,
        db_session: AsyncSession,
        service: ReferralService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        generated = iter(["itrx_TUI", "AB12cd34"])
        monkeypatch.setattr(
            "app.services.referral.secrets.token_urlsafe",
            lambda _: next(generated),
        )

        code = await service._generate_unique_code(db_session)

        assert code == "AB12cd34"

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

    async def test_batch_generation_retries_when_generated_code_already_exists(
        self,
        db_session: AsyncSession,
        service: ReferralService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        existing = User(telegram_id=410, username="existing", referral_code="DUPLICAT")
        missing = User(telegram_id=420, username="missing", referral_code=None)
        db_session.add_all([existing, missing])
        await db_session.flush()

        generated = iter(["DUPLICAT-collision", "UNIQUE12-fresh"])
        monkeypatch.setattr(
            "app.services.referral.secrets.token_urlsafe",
            lambda _: next(generated),
        )

        count = await service.generate_batch_referral_codes(db_session)

        assert count == 1
        await db_session.refresh(missing)
        assert missing.referral_code == "UNIQUE12"


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

        result = await service.bind_referral(db_session, referred, code)

        assert result.referred_by == referrer.id

    async def test_bind_rejects_invalid_code(
        self,
        db_session: AsyncSession,
        referred: User,
        service: ReferralService,
    ) -> None:
        with pytest.raises(AntExException, match="Неверный реферальный код"):
            await service.bind_referral(db_session, referred, "INVALID123")

    async def test_bind_rejects_nonexistent_eight_char_code(
        self,
        db_session: AsyncSession,
        referred: User,
        service: ReferralService,
    ) -> None:
        with pytest.raises(AntExException, match="Неверный реферальный код"):
            await service.bind_referral(db_session, referred, "A7kP2mX9")

    async def test_bind_does_not_rewrite_existing_referrer(
        self,
        db_session: AsyncSession,
        referred: User,
        service: ReferralService,
    ) -> None:
        referrer_one = User(telegram_id=310, username="ref_one", referral_code="hF84LmQz")
        referrer_two = User(telegram_id=320, username="ref_two", referral_code="N2vX8aBc")
        db_session.add_all([referrer_one, referrer_two])
        await db_session.flush()

        await service.bind_referral(db_session, referred, "hF84LmQz")
        result = await service.bind_referral(db_session, referred, "N2vX8aBc")

        assert result.referred_by == referrer_one.id

    async def test_bind_rejects_direct_mutual_referral(
        self,
        db_session: AsyncSession,
        service: ReferralService,
    ) -> None:
        user_a = User(telegram_id=330, username="user_a", referral_code="pQ7Rk91T")
        user_b = User(telegram_id=340, username="user_b", referral_code="Xz4Lm8Pw")
        db_session.add_all([user_a, user_b])
        await db_session.flush()

        await service.bind_referral(db_session, user_b, "pQ7Rk91T")

        with pytest.raises(AntExException) as exc_info:
            await service.bind_referral(db_session, user_a, "Xz4Lm8Pw")
        assert exc_info.value.code == "MUTUAL_REFERRAL"

    async def test_bind_allows_regular_chain(
        self,
        db_session: AsyncSession,
        service: ReferralService,
    ) -> None:
        user_a = User(telegram_id=350, username="chain_a", referral_code="3KdVq7Rn")
        user_b = User(telegram_id=360, username="chain_b", referral_code="Y9mNc2Lp")
        user_c = User(telegram_id=370, username="chain_c")
        db_session.add_all([user_a, user_b, user_c])
        await db_session.flush()

        await service.bind_referral(db_session, user_b, "3KdVq7Rn")
        await service.bind_referral(db_session, user_c, "Y9mNc2Lp")

        assert user_b.referred_by == user_a.id
        assert user_c.referred_by == user_b.id


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

        # Начислить ATXG рефереру за реферала
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
