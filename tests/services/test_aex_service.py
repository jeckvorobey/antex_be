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


class TestAexServiceDebitReserved:
    """TDD: debit_reserved — списание из reserved (завершение sale)."""

    async def test_debit_reserved_deducts_from_reserved(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("40"))
        entry = await service.debit_reserved(db_session, user.id, Decimal("40"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("60")
        assert wallet.balance_reserved == Decimal("0")
        assert entry.amount == Decimal("-40")
        assert entry.entry_type == "debit"

    async def test_debit_reserved_partial(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("40"))
        entry = await service.debit_reserved(db_session, user.id, Decimal("15"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("60")
        assert wallet.balance_reserved == Decimal("25")
        assert entry.amount == Decimal("-15")

    async def test_debit_reserved_rejects_insufficient_reserved(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("10"))

        with pytest.raises(AntExException, match="Reserved balance insufficient"):
            await service.debit_reserved(db_session, user.id, Decimal("20"))

    async def test_debit_reserved_rejects_zero_amount(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        with pytest.raises(AntExException, match="Amount must be positive"):
            await service.debit_reserved(db_session, user.id, Decimal("0"))

    async def test_debit_reserved_rejects_negative_amount(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        with pytest.raises(AntExException, match="Amount must be positive"):
            await service.debit_reserved(db_session, user.id, Decimal("-5"))

    async def test_full_lifecycle_hold_debit_reserved(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Полный цикл: credit → hold → debit_reserved."""
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("50"))
        await service.debit_reserved(db_session, user.id, Decimal("50"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("50")
        assert wallet.balance_reserved == Decimal("0")

    async def test_debit_reserved_no_hold_fails(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """debit_reserved без hold должен падать."""
        await service.credit(db_session, user.id, Decimal("100"))

        with pytest.raises(AntExException, match="Reserved balance insufficient"):
            await service.debit_reserved(db_session, user.id, Decimal("50"))


class TestAexServiceDoubleReserve:
    """TDD: проверка что повторный hold не дает продать больше чем есть."""

    async def test_double_hold_limited_by_available(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("80"))

        with pytest.raises(AntExException, match="Insufficient AEX balance"):
            await service.hold(db_session, user.id, Decimal("30"))

    async def test_hold_after_partial_release(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """После release часть available возвращается, можно снова hold."""
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("80"))
        await service.release(db_session, user.id, Decimal("30"))

        # Теперь available = 50, reserved = 50
        await service.hold(db_session, user.id, Decimal("20"))
        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("30")
        assert wallet.balance_reserved == Decimal("70")


class TestAexServiceReleaseAfterDebit:
    """TDD: release после debit_reserved — должен вернуть только остаток reserved."""

    async def test_release_after_partial_debit(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("40"))
        await service.debit_reserved(db_session, user.id, Decimal("25"))

        # reserved = 15, release должен работать на 15
        entry = await service.release(db_session, user.id, Decimal("15"))
        assert entry.entry_type == "release"

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("75")
        assert wallet.balance_reserved == Decimal("0")

    async def test_release_full_reserved_after_debit_fails(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Нельзя release больше чем осталось в reserved после debit."""
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("40"))
        await service.debit_reserved(db_session, user.id, Decimal("40"))

        with pytest.raises(AntExException, match="Reserved balance insufficient"):
            await service.release(db_session, user.id, Decimal("10"))


class TestAexServiceConcurrentEdgeCases:
    """TDD: edge cases для concurrent операций."""

    async def test_hold_exactly_available_balance(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Hold на весь available баланс — граничный случай."""
        await service.credit(db_session, user.id, Decimal("100"))
        entry = await service.hold(db_session, user.id, Decimal("100"))

        assert entry.amount == Decimal("100")
        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("0")
        assert wallet.balance_reserved == Decimal("100")

    async def test_release_exactly_reserved(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Release на весь reserved — граничный случай."""
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("50"))
        entry = await service.release(db_session, user.id, Decimal("50"))

        assert entry.amount == Decimal("50")
        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("100")
        assert wallet.balance_reserved == Decimal("0")

    async def test_multiple_hold_release_cycles(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Несколько циклов hold/release не ломают баланс."""
        await service.credit(db_session, user.id, Decimal("100"))

        await service.hold(db_session, user.id, Decimal("30"))
        await service.release(db_session, user.id, Decimal("30"))
        await service.hold(db_session, user.id, Decimal("50"))
        await service.release(db_session, user.id, Decimal("20"))
        await service.hold(db_session, user.id, Decimal("10"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("60")
        assert wallet.balance_reserved == Decimal("40")
        # total = 100 (invariant)
        assert wallet.balance_available + wallet.balance_reserved == Decimal("100")

    async def test_balance_never_negative_after_debit(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Баланс не может уйти в минус."""
        await service.credit(db_session, user.id, Decimal("100"))
        await service.debit(db_session, user.id, Decimal("100"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available >= Decimal("0")

    async def test_balance_never_negative_after_hold(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Reserved не может уйти в минус."""
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("100"))
        await service.release(db_session, user.id, Decimal("100"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_reserved >= Decimal("0")
        assert wallet.balance_available == Decimal("100")

    async def test_full_sale_lifecycle_with_ledger(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Полный sale lifecycle: credit → hold → debit_reserved. Проверяем ledger."""
        await service.credit(db_session, user.id, Decimal("100"), description="init")
        await service.hold(db_session, user.id, Decimal("50"), description="reserve")
        await service.debit_reserved(
            db_session, user.id, Decimal("50"), description="sale_complete"
        )

        from app.repositories.aex import AexLedgerEntryRepository, AexWalletRepository

        wallet = await AexWalletRepository(db_session).get_by_user_id(user.id)
        entries = await AexLedgerEntryRepository(db_session).get_by_wallet(wallet.id)

        assert len(entries) == 3
        types = [e.entry_type for e in entries]
        assert types == ["debit", "hold", "credit"]  # DESC order
        assert wallet.balance_available == Decimal("50")
        assert wallet.balance_reserved == Decimal("0")

    async def test_cancel_after_hold_returns_balance(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Отмена после hold (до debit) возвращает баланс через release."""
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("40"))

        # Cancel = release
        await service.release(db_session, user.id, Decimal("40"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("100")
        assert wallet.balance_reserved == Decimal("0")

    async def test_partial_cancel_after_hold(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        """Частичная отмена: hold 40, release 15, debit_reserved 25."""
        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("40"))
        await service.release(db_session, user.id, Decimal("15"))
        await service.debit_reserved(db_session, user.id, Decimal("25"))

        wallet = await service.get_balance(db_session, user.id)
        assert wallet.balance_available == Decimal("75")
        assert wallet.balance_reserved == Decimal("0")


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


class TestAexServiceOrderWithdrawalIdempotency:
    """TDD: операции вывода AEX идемпотентны по order id."""

    async def test_hold_order_withdrawal_is_idempotent_by_order_id(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("1000"))

        first = await service.hold_order_withdrawal(db_session, user.id, Decimal("400"), order_id=7)
        second = await service.hold_order_withdrawal(
            db_session, user.id, Decimal("400"), order_id=7
        )

        wallet = await service.get_balance(db_session, user.id)
        assert first.id == second.id
        assert wallet.balance_available == Decimal("600")
        assert wallet.balance_reserved == Decimal("400")

    async def test_debit_order_withdrawal_is_idempotent_by_order_id(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("1000"))
        await service.hold_order_withdrawal(db_session, user.id, Decimal("400"), order_id=7)

        first = await service.debit_order_withdrawal(
            db_session, user.id, Decimal("400"), order_id=7
        )
        second = await service.debit_order_withdrawal(
            db_session, user.id, Decimal("400"), order_id=7
        )

        wallet = await service.get_balance(db_session, user.id)
        assert first.id == second.id
        assert wallet.balance_available == Decimal("600")
        assert wallet.balance_reserved == Decimal("0")

    async def test_release_order_withdrawal_is_idempotent_by_order_id(
        self, db_session: AsyncSession, user: User, service: AexService
    ) -> None:
        await service.credit(db_session, user.id, Decimal("1000"))
        await service.hold_order_withdrawal(db_session, user.id, Decimal("400"), order_id=7)

        first = await service.release_order_withdrawal(
            db_session, user.id, Decimal("400"), order_id=7
        )
        second = await service.release_order_withdrawal(
            db_session, user.id, Decimal("400"), order_id=7
        )

        wallet = await service.get_balance(db_session, user.id)
        assert first.id == second.id
        assert wallet.balance_available == Decimal("1000")
        assert wallet.balance_reserved == Decimal("0")
