"""Тесты реферальной программы ATXG."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.enums.country import Country
from app.models.attribution import UserAcquisition
from app.models.rate import Rate
from app.models.user import User
from app.repositories.aex import (
    AexLedgerEntryRepository,
    AexWalletRepository,
)
from app.services.aex import AexService
from app.services.aex_rate import AexRateService
from app.services.referral import ReferralService

# ── Helpers ──────────────────────────────────────────────────────────


async def create_user(db, **kwargs) -> User:
    defaults = {"telegram_id": 100000, "first_name": "Test"}
    defaults.update(kwargs)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


# ── Referral Code Generation ─────────────────────────────────────────


@pytest.mark.asyncio
class TestReferralCodeService:
    async def test_get_or_create_referral_code_new(self, db_session):
        user = await create_user(db_session, telegram_id=200001)
        assert user.referral_code is None

        service = ReferralService()
        code = await service.get_or_create_referral_code(db_session, user)

        assert code is not None
        assert len(code) > 0
        assert user.referral_code == code

    async def test_get_or_create_referral_code_existing(self, db_session):
        user = await create_user(db_session, telegram_id=200002, referral_code="EXISTING")
        service = ReferralService()
        code = await service.get_or_create_referral_code(db_session, user)
        assert code == "EXISTING"


# ── Referral Binding ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReferralBinding:
    async def test_bind_referral_success(self, db_session):
        referrer = await create_user(db_session, telegram_id=300001, referral_code="A7kP2mX9")
        referred = await create_user(db_session, telegram_id=300002)

        service = ReferralService()
        await service.bind_referral(db_session, referred, "A7kP2mX9")

        ua = (
            await db_session.execute(
                select(UserAcquisition).where(UserAcquisition.user_id == referred.id)
            )
        ).scalar_one_or_none()
        assert ua is not None
        assert ua.referrer_user_id == referrer.id

    async def test_bind_referral_already_bound(self, db_session):
        referrer = await create_user(db_session, telegram_id=300003, referral_code="hF84LmQz")
        referred = await create_user(db_session, telegram_id=300004)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        service = ReferralService()
        with pytest.raises(Exception) as exc_info:
            await service.bind_referral(db_session, referred, "hF84LmQz")
        assert exc_info.value.code == "REFERRAL_EXISTING_USER"

    async def test_bind_referral_invalid_code(self, db_session):
        user = await create_user(db_session, telegram_id=300005)
        service = ReferralService()
        with pytest.raises(Exception) as exc_info:
            await service.bind_referral(db_session, user, "NONEXISTENT")
        assert exc_info.value.code == "INVALID_REFERRAL_CODE"

    async def test_bind_referral_self(self, db_session):
        user = await create_user(db_session, telegram_id=300006, referral_code="N2vX8aBc")
        service = ReferralService()
        with pytest.raises(Exception) as exc_info:
            await service.bind_referral(db_session, user, "N2vX8aBc")
        assert exc_info.value.code == "SELF_REFERRAL"

    async def test_get_referral_list(self, db_session):
        referrer = await create_user(db_session, telegram_id=300007, referral_code="pQ7Rk91T")
        referred1 = await create_user(db_session, telegram_id=300008)
        referred2 = await create_user(db_session, telegram_id=300009)
        db_session.add(
            UserAcquisition(
                user_id=referred1.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        db_session.add(
            UserAcquisition(
                user_id=referred2.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        service = ReferralService()
        referrals = await service.get_referral_list(db_session, referrer)
        assert len(referrals) == 2


# ── Wallet Repository ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAexWalletRepository:
    async def test_get_or_create_new(self, db_session):
        user = await create_user(db_session, telegram_id=400001)
        repo = AexWalletRepository(db_session)
        wallet = await repo.get_or_create(user.id)

        assert wallet.user_id == user.id
        assert wallet.balance_available == Decimal("0")
        assert wallet.balance_reserved == Decimal("0")

    async def test_get_or_create_existing(self, db_session):
        user = await create_user(db_session, telegram_id=400002)
        repo = AexWalletRepository(db_session)
        wallet1 = await repo.create(
            user_id=user.id,
            balance_available=Decimal("100"),
            balance_reserved=Decimal("0"),
        )
        wallet2 = await repo.get_or_create(user.id)
        assert wallet1.id == wallet2.id


# ── ATXG Service: Credit/Debit ────────────────────────────────────────


@pytest.mark.asyncio
class TestAexServiceOperations:
    async def test_credit(self, db_session):
        user = await create_user(db_session, telegram_id=500001)
        service = AexService()
        entry = await service.credit(
            db_session,
            user.id,
            Decimal("50.5"),
            reference_type="test",
            description="Test credit",
        )
        assert entry.amount == Decimal("50.5")

        wallet = await AexWalletRepository(db_session).get_by_user_id(user.id)
        assert wallet.balance_available == Decimal("50.5")

    async def test_credit_negative(self, db_session):
        user = await create_user(db_session, telegram_id=500002)
        service = AexService()
        with pytest.raises(Exception) as exc_info:
            await service.credit(db_session, user.id, Decimal("-10"))
        assert exc_info.value.code == "INVALID_AMOUNT"

    async def test_debit_success(self, db_session):
        user = await create_user(db_session, telegram_id=500003)
        service = AexService()
        await service.credit(db_session, user.id, Decimal("100"))
        entry = await service.debit(db_session, user.id, Decimal("30"))
        assert entry.amount == Decimal("-30")

        wallet = await AexWalletRepository(db_session).get_by_user_id(user.id)
        assert wallet.balance_available == Decimal("70")

    async def test_debit_insufficient(self, db_session):
        user = await create_user(db_session, telegram_id=500004)
        service = AexService()
        await service.credit(db_session, user.id, Decimal("10"))
        with pytest.raises(Exception) as exc_info:
            await service.debit(db_session, user.id, Decimal("50"))
        assert exc_info.value.code == "INSUFFICIENT_FUNDS"

    async def test_hold(self, db_session):
        user = await create_user(db_session, telegram_id=500005)
        service = AexService()
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("40"))

        wallet = await AexWalletRepository(db_session).get_by_user_id(user.id)
        assert wallet.balance_available == Decimal("60")
        assert wallet.balance_reserved == Decimal("40")

    async def test_release(self, db_session):
        user = await create_user(db_session, telegram_id=500006)
        service = AexService()
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("40"))
        await service.release(db_session, user.id, Decimal("20"))

        wallet = await AexWalletRepository(db_session).get_by_user_id(user.id)
        assert wallet.balance_available == Decimal("80")
        assert wallet.balance_reserved == Decimal("20")

    async def test_get_balance(self, db_session):
        user = await create_user(db_session, telegram_id=500007)
        service = AexService()
        await service.credit(db_session, user.id, Decimal("100"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("100")

    async def test_get_operations(self, db_session):
        user = await create_user(db_session, telegram_id=500008)
        service = AexService()
        await service.credit(db_session, user.id, Decimal("50"))
        await service.credit(db_session, user.id, Decimal("30"))

        entries, total = await service.get_operations(db_session, user.id)
        assert total == 2
        assert len(entries) == 2


# ── ATXG Rate Service ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAexRateService:
    async def test_get_global_rate_creates_default(self, db_session):
        service = AexRateService()
        rate = await service.get_global_rate(db_session)
        assert rate.global_rate == Decimal("0.002")

    async def test_update_global_rate(self, db_session):
        service = AexRateService()
        rate = await service.update_global_rate(db_session, Decimal("0.005"))
        assert rate.global_rate == Decimal("0.005")

    async def test_get_effective_rate_global(self, db_session):
        user = await create_user(db_session, telegram_id=600001)
        service = AexRateService()
        rate = await service.get_effective_rate(db_session, user.id)
        assert rate == Decimal("0.002")

    async def test_get_effective_rate_personal(self, db_session):
        user = await create_user(db_session, telegram_id=600002)
        service = AexRateService()
        await service.set_personal_rate(db_session, user.id, Decimal("0.01"))
        rate = await service.get_effective_rate(db_session, user.id)
        assert rate == Decimal("0.01")

    async def test_set_personal_rate_invalid(self, db_session):
        user = await create_user(db_session, telegram_id=600003)
        service = AexRateService()
        with pytest.raises(Exception) as exc_info:
            await service.set_personal_rate(db_session, user.id, Decimal("-1"))
        assert exc_info.value.code == "INVALID_RATE"


# ── Referral Bonus ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReferralBonus:
    async def test_credit_referral_bonus(self, db_session):
        referrer = await create_user(db_session, telegram_id=700001, referral_code="BONUS1")
        referred = await create_user(db_session, telegram_id=700002)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=1,
            order_amount=Decimal("10000"),
            referred_user_id=referred.id,
        )

        assert aex_amount == Decimal("20.000000")  # 10000 * 0.002

        # Check wallet balance
        wallet = await AexWalletRepository(db_session).get_by_user_id(referrer.id)
        assert wallet is not None
        assert wallet.balance_available == Decimal("20.000000")

    async def test_credit_referral_bonus_rub_order_uses_usdt_equivalent(self, db_session):
        referrer = await create_user(db_session, telegram_id=700010, referral_code="BONUSRUB")
        referred = await create_user(db_session, telegram_id=700011)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()
        db_session.add_all(
            [
                Rate(currency="USDTTHB", price=35.5, margin=3.0, country=Country.THAILAND),
                Rate(currency="RUBTHB", price=0.355, margin=3.0, country=Country.THAILAND),
            ]
        )
        await db_session.flush()

        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=3,
            order_amount=Decimal("100000"),
            referred_user_id=referred.id,
            currency_sell="RUB",
            currency_buy="THB",
        )

        assert aex_amount == Decimal("2.000000")

    async def test_credit_referral_bonus_no_referrer(self, db_session):
        user = await create_user(db_session, telegram_id=700003)
        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=1,
            order_amount=Decimal("10000"),
            referred_user_id=user.id,
        )
        assert aex_amount == Decimal("0")

    async def test_credit_referral_bonus_personal_rate(self, db_session):
        referrer = await create_user(db_session, telegram_id=700004, referral_code="BONUS2")
        referred = await create_user(db_session, telegram_id=700005)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        # Set personal rate to 1%
        rate_service = AexRateService()
        await rate_service.set_personal_rate(db_session, referrer.id, Decimal("0.01"))

        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=2,
            order_amount=Decimal("5000"),
            referred_user_id=referred.id,
        )

        assert aex_amount == Decimal("50.000000")  # 5000 * 0.01

    async def test_credit_referral_bonus_creates_ledger(self, db_session):
        referrer = await create_user(db_session, telegram_id=700006, referral_code="BONUS3")
        referred = await create_user(db_session, telegram_id=700007)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        service = ReferralService()
        await service.credit_referral_bonus(
            db_session,
            order_id=42,
            order_amount=Decimal("10000"),
            referred_user_id=referred.id,
        )

        # Check ledger entry
        wallet = await AexWalletRepository(db_session).get_by_user_id(referrer.id)
        ledger_repo = AexLedgerEntryRepository(db_session)
        entries = await ledger_repo.get_by_wallet(wallet.id)
        assert len(entries) == 1
        assert entries[0].entry_type == "credit"
        assert entries[0].reference_type == "referral"
        assert entries[0].reference_id == "42"

    async def test_credit_referral_bonus_is_idempotent_by_order(self, db_session):
        referrer = await create_user(db_session, telegram_id=700008, referral_code="BONUS4")
        referred = await create_user(db_session, telegram_id=700009)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        service = ReferralService()
        first = await service.credit_referral_bonus(
            db_session,
            order_id=77,
            order_amount=Decimal("10000"),
            referred_user_id=referred.id,
        )
        second = await service.credit_referral_bonus(
            db_session,
            order_id=77,
            order_amount=Decimal("10000"),
            referred_user_id=referred.id,
        )

        wallet = await AexWalletRepository(db_session).get_by_user_id(referrer.id)
        ledger_repo = AexLedgerEntryRepository(db_session)
        entries = await ledger_repo.get_by_wallet(wallet.id)

        assert first == Decimal("20.000000")
        assert second == Decimal("20.00000000")
        assert wallet.balance_available == Decimal("20.000000")
        assert len([entry for entry in entries if entry.reference_type == "referral"]) == 1
