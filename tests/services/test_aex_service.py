"""TDD тесты для AexService."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AntExException
from app.models.user import User
from app.services.aex import AexService


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    user = User(telegram_id=100, username="aex_user", first_name="AEX")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def service() -> AexService:
    return AexService()


class TestAexServiceGetOrCreateWallet:
    async def test_creates_wallet_for_new_user(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        wallet = await service.get_or_create_wallet(db_session, user.id)

        assert wallet.id is not None
        assert wallet.user_id == user.id
        assert wallet.balance_available == Decimal("0")
        assert wallet.balance_reserved == Decimal("0")

    async def test_returns_existing_wallet(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        wallet1 = await service.get_or_create_wallet(db_session, user.id)
        wallet2 = await service.get_or_create_wallet(db_session, user.id)

        assert wallet1.id == wallet2.id


class TestAexServiceCredit:
    async def test_credit_increases_balance(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        entry = await service.credit(db_session, user.id, Decimal("100"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("100")
        assert entry.amount == Decimal("100")
        assert entry.entry_type == "credit"

    async def test_credit_with_reference(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        entry = await service.credit(
            db_session,
            user.id,
            Decimal("50"),
            reference_type="referral",
            reference_id="42",
            description="Referral bonus",
        )

        assert entry.reference_type == "referral"
        assert entry.reference_id == "42"
        assert entry.description == "Referral bonus"

    async def test_credit_rejects_zero_amount(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        with pytest.raises(AntExException, match="Amount must be positive"):
            await service.credit(db_session, user.id, Decimal("0"))

    async def test_credit_rejects_negative_amount(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        with pytest.raises(AntExException, match="Amount must be positive"):
            await service.credit(db_session, user.id, Decimal("-10"))


class TestAexServiceDebit:
    async def test_debit_decreases_balance(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"))
        entry = await service.debit(db_session, user.id, Decimal("30"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("70")
        assert entry.amount == Decimal("-30")
        assert entry.entry_type == "debit"

    async def test_debit_rejects_insufficient_funds(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("10"))

        with pytest.raises(AntExException, match="Insufficient AEX balance"):
            await service.debit(db_session, user.id, Decimal("20"))

    async def test_debit_rejects_zero_amount(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        with pytest.raises(AntExException, match="Amount must be positive"):
            await service.debit(db_session, user.id, Decimal("0"))


class TestAexServiceHoldRelease:
    async def test_hold_moves_to_reserved(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"))
        entry = await service.hold(db_session, user.id, Decimal("40"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("60")
        assert wallet.balance_reserved == Decimal("40")
        assert entry.entry_type == "hold"

    async def test_release_moves_back_to_available(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("40"))
        entry = await service.release(db_session, user.id, Decimal("20"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("80")
        assert wallet.balance_reserved == Decimal("20")
        assert entry.entry_type == "release"

    async def test_hold_rejects_insufficient_available(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("10"))

        with pytest.raises(AntExException, match="Insufficient AEX balance"):
            await service.hold(db_session, user.id, Decimal("20"))

    async def test_release_rejects_insufficient_reserved(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("10"))

        with pytest.raises(AntExException, match="Reserved balance insufficient"):
            await service.release(db_session, user.id, Decimal("20"))


class TestAexServiceGetOperations:
    async def test_get_operations_returns_entries(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"), description="First")
        await service.credit(db_session, user.id, Decimal("50"), description="Second")

        entries, total = await service.get_operations(db_session, user.id)

        assert len(entries) == 2
        assert total == 2
        # Desc order: newest first
        assert entries[0].description == "Second"
        assert entries[1].description == "First"

    async def test_get_operations_with_pagination(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        for _i in range(5):
            await service.credit(db_session, user.id, Decimal("10"))

        entries, total = await service.get_operations(db_session, user.id, limit=2, offset=1)

        assert len(entries) == 2
        assert total == 5

    async def test_get_operations_empty_for_no_wallet(
        self, db_session: AsyncSession, service: AexService
    ) -> None:
        entries, total = await service.get_operations(db_session, 999999)

        assert entries == []
        assert total == 0
