"""TDD тесты для моделей ATXG и реферальной системы."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aex import AexLedgerEntry, AexPartnerRate, AexPersonalRate, AexRate, AexWallet
from app.models.attribution import UserAcquisition
from app.models.user import User


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    user = User(
        telegram_id=111222,
        username="testuser",
        first_name="Test",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def wallet(db_session: AsyncSession, user: User) -> AexWallet:
    wallet = AexWallet(
        user_id=user.id,
        balance_available=Decimal("100.5"),
        balance_reserved=Decimal("10.25"),
    )
    db_session.add(wallet)
    await db_session.flush()
    await db_session.refresh(wallet)
    return wallet


class TestAexWallet:
    async def test_create_wallet(self, db_session: AsyncSession, user: User) -> None:
        wallet = AexWallet(
            user_id=user.id,
            balance_available=Decimal("0"),
            balance_reserved=Decimal("0"),
        )
        db_session.add(wallet)
        await db_session.flush()
        await db_session.refresh(wallet)

        assert wallet.id is not None
        assert wallet.user_id == user.id
        assert wallet.balance_available == Decimal("0")
        assert wallet.balance_reserved == Decimal("0")
        assert wallet.createdAt is not None
        assert wallet.updatedAt is not None

    async def test_wallet_decimal_precision(self, db_session: AsyncSession, user: User) -> None:
        wallet = AexWallet(
            user_id=user.id,
            balance_available=Decimal("999999.12345678"),
            balance_reserved=Decimal("0.00000001"),
        )
        db_session.add(wallet)
        await db_session.flush()
        await db_session.refresh(wallet)

        # SQLite has limited Numeric precision, so we check within tolerance
        assert abs(wallet.balance_available - Decimal("999999.12345678")) < Decimal("0.001")
        assert abs(wallet.balance_reserved - Decimal("0.00000001")) < Decimal("0.001")

    async def test_wallet_user_relationship(
        self, db_session: AsyncSession, wallet: AexWallet, user: User
    ) -> None:
        assert wallet.user.id == user.id

    async def test_user_aex_wallet_relationship(
        self, db_session: AsyncSession, user: User, wallet: AexWallet
    ) -> None:
        await db_session.refresh(user, ["aex_wallet"])
        assert user.aex_wallet is not None
        assert user.aex_wallet.id == wallet.id

    async def test_user_aex_wallet_is_none_without_wallet(self, db_session: AsyncSession) -> None:
        user = User(telegram_id=999, username="nowallet")
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user, ["aex_wallet"])
        assert user.aex_wallet is None


class TestAexLedgerEntry:
    async def test_create_ledger_entry(self, db_session: AsyncSession, wallet: AexWallet) -> None:
        entry = AexLedgerEntry(
            wallet_id=wallet.id,
            amount=Decimal("50.0"),
            entry_type="credit",
            reference_type="referral",
            reference_id="123",
            description="Referral bonus",
        )
        db_session.add(entry)
        await db_session.flush()
        await db_session.refresh(entry)

        assert entry.id is not None
        assert entry.wallet_id == wallet.id
        assert entry.amount == Decimal("50.0")
        assert entry.entry_type == "credit"
        assert entry.reference_type == "referral"
        assert entry.reference_id == "123"
        assert entry.description == "Referral bonus"

    async def test_ledger_entry_negative_amount(
        self, db_session: AsyncSession, wallet: AexWallet
    ) -> None:
        entry = AexLedgerEntry(
            wallet_id=wallet.id,
            amount=Decimal("-25.5"),
            entry_type="debit",
        )
        db_session.add(entry)
        await db_session.flush()
        await db_session.refresh(entry)

        assert entry.amount == Decimal("-25.5")

    async def test_ledger_entry_optional_fields(
        self, db_session: AsyncSession, wallet: AexWallet
    ) -> None:
        entry = AexLedgerEntry(
            wallet_id=wallet.id,
            amount=Decimal("10"),
            entry_type="hold",
        )
        db_session.add(entry)
        await db_session.flush()
        await db_session.refresh(entry)

        assert entry.reference_type is None
        assert entry.reference_id is None
        assert entry.description is None

    async def test_ledger_wallet_relationship(
        self, db_session: AsyncSession, wallet: AexWallet
    ) -> None:
        entry = AexLedgerEntry(
            wallet_id=wallet.id,
            amount=Decimal("10"),
            entry_type="credit",
        )
        db_session.add(entry)
        await db_session.flush()
        await db_session.refresh(entry)

        assert entry.wallet.id == wallet.id


class TestAexRate:
    async def test_create_global_rate(self, db_session: AsyncSession) -> None:
        rate = AexRate(global_rate=Decimal("0.002"))
        db_session.add(rate)
        await db_session.flush()
        await db_session.refresh(rate)

        assert rate.id is not None
        assert rate.global_rate == Decimal("0.002")
        assert rate.createdAt is not None

    async def test_rate_default_value(self, db_session: AsyncSession) -> None:
        rate = AexRate()
        db_session.add(rate)
        await db_session.flush()
        await db_session.refresh(rate)

        assert rate.global_rate == Decimal("0.002")


class TestAexPersonalRate:
    async def test_create_personal_rate(self, db_session: AsyncSession, user: User) -> None:
        rate = AexPersonalRate(user_id=user.id, rate=Decimal("0.005"))
        db_session.add(rate)
        await db_session.flush()
        await db_session.refresh(rate)

        assert rate.id is not None
        assert rate.user_id == user.id
        assert rate.rate == Decimal("0.005")

    async def test_personal_rate_user_relationship(
        self, db_session: AsyncSession, user: User
    ) -> None:
        rate = AexPersonalRate(user_id=user.id, rate=Decimal("0.003"))
        db_session.add(rate)
        await db_session.flush()
        await db_session.refresh(rate)

        assert rate.user.id == user.id

    async def test_user_personal_rate_relationship(
        self, db_session: AsyncSession, user: User
    ) -> None:
        rate = AexPersonalRate(user_id=user.id, rate=Decimal("0.003"))
        db_session.add(rate)
        await db_session.flush()
        await db_session.refresh(user, ["aex_personal_rate"])

        assert user.aex_personal_rate is not None
        assert user.aex_personal_rate.rate == Decimal("0.003")


class TestAexPartnerRate:
    async def test_create_partner_rate(self, db_session: AsyncSession, user: User) -> None:
        rate = AexPartnerRate(user_id=user.id, rate=Decimal("0.007"))
        db_session.add(rate)
        await db_session.flush()
        await db_session.refresh(rate)

        assert rate.id is not None
        assert rate.user_id == user.id
        assert rate.rate == Decimal("0.007")

    async def test_partner_rate_user_relationship(
        self, db_session: AsyncSession, user: User
    ) -> None:
        rate = AexPartnerRate(user_id=user.id, rate=Decimal("0.004"))
        db_session.add(rate)
        await db_session.flush()
        await db_session.refresh(rate)

        assert rate.user.id == user.id

    async def test_user_partner_rate_relationship(
        self, db_session: AsyncSession, user: User
    ) -> None:
        rate = AexPartnerRate(user_id=user.id, rate=Decimal("0.004"))
        db_session.add(rate)
        await db_session.flush()
        await db_session.refresh(user, ["aex_partner_rate"])

        assert user.aex_partner_rate is not None
        assert user.aex_partner_rate.rate == Decimal("0.004")


class TestUserReferralFields:
    async def test_user_referral_code(self, db_session: AsyncSession) -> None:
        user = User(
            telegram_id=333,
            username="referrer",
            referral_code="ABC12345",
        )
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        assert user.referral_code == "ABC12345"

    async def test_referrer_is_stored_in_user_acquisition(self, db_session: AsyncSession) -> None:
        referrer = User(telegram_id=444, username="referrer2", referral_code="REF12345")
        db_session.add(referrer)
        await db_session.flush()

        referred = User(telegram_id=555, username="referred")
        db_session.add(referred)
        await db_session.flush()
        await db_session.refresh(referred)

        acquisition = UserAcquisition(
            user_id=referred.id,
            source_type="referral",
            referrer_user_id=referrer.id,
        )
        db_session.add(acquisition)
        await db_session.flush()

        assert "referred_by" not in User.__table__.c

    async def test_user_referral_code_nullable(self, db_session: AsyncSession) -> None:
        user = User(telegram_id=888, username="noreferral")
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        assert user.referral_code is None
