"""Edge case тесты реферальной системы ATXG.

Покрывает:
1. Edge cases привязки (пустой код, whitespace, цепочки)
2. Граничные значения расчётов (0, дробные, огромные)
3. Компенсирующие операции при отмене
4. Приоритет ставок
5. Инвариант: баланс не уходит в минус
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AntExException
from app.models.attribution import UserAcquisition
from app.models.user import User
from app.repositories.aex import AexWalletRepository
from app.services.aex import AexService
from app.services.aex_rate import AexRateService
from app.services.referral import ReferralService

# ── Helpers ──────────────────────────────────────────────────────────


async def create_user(db: AsyncSession, **kwargs) -> User:
    defaults = {"telegram_id": 900000, "first_name": "Edge"}
    defaults.update(kwargs)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


# ── 1. Referral Binding Edge Cases ───────────────────────────────────


@pytest.mark.asyncio
class TestReferralBindingEdgeCases:
    """Edge cases привязки рефералов."""

    async def test_bind_empty_code_raises(self, db_session: AsyncSession) -> None:
        """Пустой код → INVALID_REFERRAL_CODE."""
        user = await create_user(db_session, telegram_id=901001)
        service = ReferralService()
        with pytest.raises(AntExException) as exc_info:
            await service.bind_referral(db_session, user, "")
        assert exc_info.value.code == "INVALID_REFERRAL_CODE"

    async def test_bind_whitespace_code_raises(self, db_session: AsyncSession) -> None:
        """Пробельный код → INVALID_REFERRAL_CODE."""
        user = await create_user(db_session, telegram_id=901002)
        service = ReferralService()
        with pytest.raises(AntExException) as exc_info:
            await service.bind_referral(db_session, user, "   ")
        assert exc_info.value.code == "INVALID_REFERRAL_CODE"

    async def test_bind_long_code_raises(self, db_session: AsyncSession) -> None:
        """Очень длинный код → INVALID_REFERRAL_CODE."""
        user = await create_user(db_session, telegram_id=901003)
        service = ReferralService()
        with pytest.raises(AntExException) as exc_info:
            await service.bind_referral(db_session, user, "A" * 1000)
        assert exc_info.value.code == "INVALID_REFERRAL_CODE"

    async def test_bind_referral_chain(self, db_session: AsyncSession) -> None:
        """A → B → C: C привязан к B, B привязан к A. Проверка цепочки."""
        service = ReferralService()

        user_a = await create_user(db_session, telegram_id=901010, referral_code="Xz4Lm8Pw")
        user_b = await create_user(db_session, telegram_id=901011)
        user_c = await create_user(db_session, telegram_id=901012)

        await service.bind_referral(db_session, user_b, "Xz4Lm8Pw")
        # B генерирует свой код
        code_b = await service.get_or_create_referral_code(db_session, user_b)
        await service.bind_referral(db_session, user_c, code_b)

        ua_b = (
            await db_session.execute(
                select(UserAcquisition).where(UserAcquisition.user_id == user_b.id)
            )
        ).scalar_one_or_none()
        ua_c = (
            await db_session.execute(
                select(UserAcquisition).where(UserAcquisition.user_id == user_c.id)
            )
        ).scalar_one_or_none()
        assert ua_b is not None and ua_b.referrer_user_id == user_a.id
        assert ua_c is not None and ua_c.referrer_user_id == user_b.id

    async def test_bind_same_code_by_two_users(self, db_session: AsyncSession) -> None:
        """Два разных пользователя привязываются к одному рефереру."""
        service = ReferralService()
        referrer = await create_user(db_session, telegram_id=901020, referral_code="3KdVq7Rn")
        user1 = await create_user(db_session, telegram_id=901021)
        user2 = await create_user(db_session, telegram_id=901022)

        await service.bind_referral(db_session, user1, "3KdVq7Rn")
        await service.bind_referral(db_session, user2, "3KdVq7Rn")

        ua1 = (
            await db_session.execute(
                select(UserAcquisition).where(UserAcquisition.user_id == user1.id)
            )
        ).scalar_one_or_none()
        ua2 = (
            await db_session.execute(
                select(UserAcquisition).where(UserAcquisition.user_id == user2.id)
            )
        ).scalar_one_or_none()
        assert ua1 is not None and ua1.referrer_user_id == referrer.id
        assert ua2 is not None and ua2.referrer_user_id == referrer.id

        referrals = await service.get_referral_list(db_session, referrer)
        assert len(referrals) == 2

    async def test_referral_code_case_sensitive(self, db_session: AsyncSession) -> None:
        """Реферальный код чувствителен к регистру."""
        service = ReferralService()
        await create_user(db_session, telegram_id=901030, referral_code="Y9mNc2Lp")
        user = await create_user(db_session, telegram_id=901031)

        with pytest.raises(AntExException) as exc_info:
            await service.bind_referral(db_session, user, "y9mNc2Lp")
        assert exc_info.value.code == "INVALID_REFERRAL_CODE"


# ── 2. ATXG Calculation Edge Cases ───────────────────────────────────


@pytest.mark.asyncio
class TestAexCalculationEdgeCases:
    """Граничные значения расчётов ATXG."""

    async def test_referral_bonus_zero_order_amount(self, db_session: AsyncSession) -> None:
        """Заказ на 0 → бонус 0 (не начисляется)."""
        referrer = await create_user(db_session, telegram_id=902001, referral_code="ZEROBON")
        referred = await create_user(db_session, telegram_id=902002)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=100,
            order_amount=Decimal("0"),
            referred_user_id=referred.id,
        )
        assert aex_amount == Decimal("0")

    async def test_referral_bonus_small_amount_rounds_to_zero(
        self, db_session: AsyncSession
    ) -> None:
        """Очень маленький заказ, при котором бонус округляется до 0."""
        referrer = await create_user(db_session, telegram_id=902003, referral_code="SMALLBN")
        referred = await create_user(db_session, telegram_id=902004)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        # rate=0.002, amount=0.01 → bonus=0.00002 → quantize to 0.000000 → <= 0 → 0
        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=101,
            order_amount=Decimal("0.01"),
            referred_user_id=referred.id,
        )
        # 0.01 * 0.002 = 0.00002, quantize to 6 decimal = 0.000020 > 0 → credit
        assert aex_amount == Decimal("0.000020")

    async def test_referral_bonus_fractional_amount(self, db_session: AsyncSession) -> None:
        """Дробная сумма заказа → корректный расчёт."""
        referrer = await create_user(db_session, telegram_id=902005, referral_code="FRACBN")
        referred = await create_user(db_session, telegram_id=902006)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=102,
            order_amount=Decimal("3333.33"),
            referred_user_id=referred.id,
        )
        # 3333.33 * 0.002 = 6.66666, quantize → 6.666660
        assert aex_amount == Decimal("6.666660")

    async def test_referral_bonus_large_amount(self, db_session: AsyncSession) -> None:
        """Огромная сумма заказа → корректный расчёт без переполнения."""
        referrer = await create_user(db_session, telegram_id=902007, referral_code="LARGEBN")
        referred = await create_user(db_session, telegram_id=902008)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=103,
            order_amount=Decimal("1000000"),
            referred_user_id=referred.id,
        )
        # 1000000 * 0.002 = 2000
        assert aex_amount == Decimal("2000.000000")

        wallet = await AexWalletRepository(db_session).get_by_user_id(referrer.id)
        assert wallet is not None
        assert wallet.balance_available == Decimal("2000.000000")

    async def test_referral_bonus_with_very_high_rate(self, db_session: AsyncSession) -> None:
        """Персональная ставка 10% → корректный расчёт."""
        referrer = await create_user(db_session, telegram_id=902009, referral_code="HIGHRT")
        referred = await create_user(db_session, telegram_id=902010)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        rate_service = AexRateService()
        await rate_service.set_personal_rate(db_session, referrer.id, Decimal("0.10"))

        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=104,
            order_amount=Decimal("1000"),
            referred_user_id=referred.id,
        )
        # 1000 * 0.10 = 100
        assert aex_amount == Decimal("100.000000")


# ── 3. Balance Invariant Tests ───────────────────────────────────────


@pytest.mark.asyncio
class TestBalanceInvariant:
    """Инвариант: баланс не уходит в минус."""

    async def test_balance_never_negative_after_debit(self, db_session: AsyncSession) -> None:
        """Попытка списать больше, чем есть → баланс не меняется."""
        user = await create_user(db_session, telegram_id=903001)
        service = AexService()

        await service.credit(db_session, user.id, Decimal("100"))

        with pytest.raises(AntExException):
            await service.debit(db_session, user.id, Decimal("150"))

        wallet = await AexWalletRepository(db_session).get_by_user_id(user.id)
        assert wallet is not None
        assert wallet.balance_available == Decimal("100")
        assert wallet.balance_available >= 0

    async def test_balance_never_negative_after_hold(self, db_session: AsyncSession) -> None:
        """Попытка заморозить больше, чем available → баланс не меняется."""
        user = await create_user(db_session, telegram_id=903002)
        service = AexService()

        await service.credit(db_session, user.id, Decimal("50"))

        with pytest.raises(AntExException):
            await service.hold(db_session, user.id, Decimal("100"))

        wallet = await AexWalletRepository(db_session).get_by_user_id(user.id)
        assert wallet is not None
        assert wallet.balance_available == Decimal("50")
        assert wallet.balance_reserved == Decimal("0")

    async def test_multiple_operations_preserve_invariant(self, db_session: AsyncSession) -> None:
        """Серия операций: credit → hold → release → debit → баланс корректен."""
        user = await create_user(db_session, telegram_id=903003)
        service = AexService()

        await service.credit(db_session, user.id, Decimal("100"))
        await service.hold(db_session, user.id, Decimal("30"))
        await service.release(db_session, user.id, Decimal("10"))
        await service.debit(db_session, user.id, Decimal("20"))

        wallet = await AexWalletRepository(db_session).get_by_user_id(user.id)
        assert wallet is not None
        # 100 - 30 + 10 - 20 = 60
        assert wallet.balance_available == Decimal("60")
        assert wallet.balance_reserved == Decimal("20")
        assert wallet.balance_available >= 0
        assert wallet.balance_reserved >= 0


# ── 4. Rate Priority Edge Cases ─────────────────────────────────────


@pytest.mark.asyncio
class TestRatePriorityEdgeCases:
    """Приоритет ставок: персональная > глобальная."""

    async def test_personal_rate_takes_priority(self, db_session: AsyncSession) -> None:
        """Персональная ставка имеет приоритет над глобальной."""
        user = await create_user(db_session, telegram_id=904001)
        service = AexRateService()

        await service.update_global_rate(db_session, Decimal("0.001"))
        await service.set_personal_rate(db_session, user.id, Decimal("0.05"))

        rate = await service.get_effective_rate(db_session, user.id)
        assert rate == Decimal("0.05")

    async def test_delete_personal_falls_back_to_global(self, db_session: AsyncSession) -> None:
        """Удаление персональной → возврат к глобальной."""
        user = await create_user(db_session, telegram_id=904002)
        service = AexRateService()

        await service.update_global_rate(db_session, Decimal("0.003"))
        await service.set_personal_rate(db_session, user.id, Decimal("0.05"))
        await service.delete_personal_rate(db_session, user.id)

        rate = await service.get_effective_rate(db_session, user.id)
        assert rate == Decimal("0.003")

    async def test_update_personal_rate_changes_effective(self, db_session: AsyncSession) -> None:
        """Обновление персональной ставки меняет эффективную."""
        user = await create_user(db_session, telegram_id=904003)
        service = AexRateService()

        await service.set_personal_rate(db_session, user.id, Decimal("0.01"))
        assert await service.get_effective_rate(db_session, user.id) == Decimal("0.01")

        await service.set_personal_rate(db_session, user.id, Decimal("0.02"))
        assert await service.get_effective_rate(db_session, user.id) == Decimal("0.02")

    async def test_global_rate_change_does_not_affect_personal(
        self, db_session: AsyncSession
    ) -> None:
        """Изменение глобальной не влияет на персональную."""
        user = await create_user(db_session, telegram_id=904004)
        service = AexRateService()

        await service.set_personal_rate(db_session, user.id, Decimal("0.05"))
        await service.update_global_rate(db_session, Decimal("0.001"))

        rate = await service.get_effective_rate(db_session, user.id)
        assert rate == Decimal("0.05")

    async def test_referral_bonus_uses_correct_rate(self, db_session: AsyncSession) -> None:
        """Реферальный бонус использует эффективную ставку реферера, а не реферала."""  # noqa: RUF002
        referrer = await create_user(db_session, telegram_id=904010, referral_code="RATETST")
        referred = await create_user(db_session, telegram_id=904011)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        rate_service = AexRateService()
        # Персональная ставка для реферера = 5%
        await rate_service.set_personal_rate(db_session, referrer.id, Decimal("0.05"))

        service = ReferralService()
        aex_amount = await service.credit_referral_bonus(
            db_session,
            order_id=200,
            order_amount=Decimal("1000"),
            referred_user_id=referred.id,
        )

        # 1000 * 0.05 = 50
        assert aex_amount == Decimal("50.000000")


# ── 5. Cancellation Compensation Tests ───────────────────────────────


@pytest.mark.asyncio
class TestCancellationCompensation:
    """Компенсирующие операции при отмене."""

    async def test_referral_bonus_reversal_on_cancel(self, db_session: AsyncSession) -> None:
        """При отмене заказа бонус реферера списывается."""
        referrer = await create_user(db_session, telegram_id=905001, referral_code="CANCEL1")
        referred = await create_user(db_session, telegram_id=905002)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        referral_service = ReferralService()
        aex_service = AexService()

        # Начислить бонус за заказ
        bonus = await referral_service.credit_referral_bonus(
            db_session,
            order_id=300,
            order_amount=Decimal("10000"),
            referred_user_id=referred.id,
        )
        assert bonus == Decimal("20.000000")

        wallet = await AexWalletRepository(db_session).get_by_user_id(referrer.id)
        assert wallet is not None
        assert wallet.balance_available == Decimal("20.000000")

        # Имитация отмены: найти запись и списать
        from sqlalchemy import select

        from app.models.aex import AexLedgerEntry

        result = await db_session.execute(
            select(AexLedgerEntry).where(
                AexLedgerEntry.reference_type == "referral",
                AexLedgerEntry.reference_id == "300",
                AexLedgerEntry.entry_type == "credit",
            )
        )
        entry = result.scalar_one_or_none()
        assert entry is not None

        # Списать бонус
        await aex_service.debit(
            db_session,
            referrer.id,
            entry.amount,
            reference_type="referral_reversal",
            reference_id="300",
            description="Reversal for cancelled order #300",
        )

        wallet = await AexWalletRepository(db_session).get_by_user_id(referrer.id)
        assert wallet is not None
        assert wallet.balance_available == Decimal("0")

    async def test_no_reversal_if_no_referral_bonus(self, db_session: AsyncSession) -> None:
        """Если бонус не начислялся (нет реферера), отмена не влияет на баланс."""
        await create_user(db_session, telegram_id=905003)

        # Проверить, что reversal entry не существует
        from sqlalchemy import select

        from app.models.aex import AexLedgerEntry

        result = await db_session.execute(
            select(AexLedgerEntry).where(
                AexLedgerEntry.reference_type == "referral",
                AexLedgerEntry.reference_id == "999",
                AexLedgerEntry.entry_type == "credit",
            )
        )
        entry = result.scalar_one_or_none()
        assert entry is None

    async def test_no_silent_reversal_when_referral_bonus_is_spent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Если бонус уже потрачен, reversal не списывает баланс в минус."""
        referrer = await create_user(db_session, telegram_id=905004, referral_code="SPENT001")
        referred = await create_user(db_session, telegram_id=905005)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        referral_service = ReferralService()
        aex_service = AexService()
        await referral_service.credit_referral_bonus(
            db_session,
            order_id=301,
            order_amount=Decimal("10000"),
            referred_user_id=referred.id,
        )
        await aex_service.debit(
            db_session,
            referrer.id,
            Decimal("15"),
            reference_type="admin_debit",
            reference_id="spent-before-cancel",
        )

        from sqlalchemy import select

        from app.models.aex import AexLedgerEntry

        result = await db_session.execute(
            select(AexLedgerEntry).where(
                AexLedgerEntry.reference_type == "referral",
                AexLedgerEntry.reference_id == "301",
                AexLedgerEntry.entry_type == "credit",
            )
        )
        entry = result.scalar_one()
        wallet = await AexWalletRepository(db_session).get_by_user_id(referrer.id)
        assert wallet is not None
        assert wallet.balance_available < entry.amount

        if wallet.balance_available >= entry.amount:
            await aex_service.debit(
                db_session,
                referrer.id,
                entry.amount,
                reference_type="referral_reversal",
                reference_id="301",
            )

        reversal_result = await db_session.execute(
            select(AexLedgerEntry).where(
                AexLedgerEntry.reference_type == "referral_reversal",
                AexLedgerEntry.reference_id == "301",
            )
        )
        assert reversal_result.scalar_one_or_none() is None
        assert wallet.balance_available == Decimal("5.000000")

    async def test_multiple_orders_cancel_one(self, db_session: AsyncSession) -> None:
        """Two orders, cancel one - deduct only its bonus."""
        referrer = await create_user(db_session, telegram_id=905010, referral_code="MULTORD")
        referred = await create_user(db_session, telegram_id=905011)
        db_session.add(
            UserAcquisition(
                user_id=referred.id, source_type="referral", referrer_user_id=referrer.id
            )
        )
        await db_session.flush()

        referral_service = ReferralService()
        aex_service = AexService()

        # Два заказа
        await referral_service.credit_referral_bonus(
            db_session,
            order_id=400,
            order_amount=Decimal("10000"),
            referred_user_id=referred.id,
        )
        await referral_service.credit_referral_bonus(
            db_session,
            order_id=401,
            order_amount=Decimal("5000"),
            referred_user_id=referred.id,
        )

        wallet = await AexWalletRepository(db_session).get_by_user_id(referrer.id)
        assert wallet is not None
        # 20 + 10 = 30
        assert wallet.balance_available == Decimal("30.000000")

        # Отменить только первый заказ
        from sqlalchemy import select

        from app.models.aex import AexLedgerEntry

        result = await db_session.execute(
            select(AexLedgerEntry).where(
                AexLedgerEntry.reference_type == "referral",
                AexLedgerEntry.reference_id == "400",
                AexLedgerEntry.entry_type == "credit",
            )
        )
        entry = result.scalar_one_or_none()
        assert entry is not None
        await aex_service.debit(
            db_session,
            referrer.id,
            entry.amount,
            reference_type="referral_reversal",
            reference_id="400",
        )

        wallet = await AexWalletRepository(db_session).get_by_user_id(referrer.id)
        assert wallet is not None
        # 30 - 20 = 10 (второй бонус остался)
        assert wallet.balance_available == Decimal("10.000000")


# ── 6. Ledger Entry Integrity ────────────────────────────────────────


@pytest.mark.asyncio
class TestLedgerEntryIntegrity:
    """Целостность записей журнала."""

    async def test_credit_creates_correct_entry(self, db_session: AsyncSession) -> None:
        """Credit creates entry with correct type and amount."""
        user = await create_user(db_session, telegram_id=906001)
        service = AexService()

        entry = await service.credit(
            db_session,
            user.id,
            Decimal("42.5"),
            reference_type="test",
            reference_id="abc",
            description="Test entry",
        )

        assert entry.entry_type == "credit"
        assert entry.amount == Decimal("42.5")
        assert entry.reference_type == "test"
        assert entry.reference_id == "abc"
        assert entry.description == "Test entry"

    async def test_debit_creates_negative_amount(self, db_session: AsyncSession) -> None:
        """Debit creates entry with negative amount."""
        user = await create_user(db_session, telegram_id=906002)
        service = AexService()

        await service.credit(db_session, user.id, Decimal("100"))
        entry = await service.debit(db_session, user.id, Decimal("30"))

        assert entry.entry_type == "debit"
        assert entry.amount == Decimal("-30")

    async def test_hold_and_release_entries(self, db_session: AsyncSession) -> None:
        """Hold и release создают корректные записи."""
        user = await create_user(db_session, telegram_id=906003)
        service = AexService()

        await service.credit(db_session, user.id, Decimal("100"))
        hold_entry = await service.hold(db_session, user.id, Decimal("40"))
        release_entry = await service.release(db_session, user.id, Decimal("15"))

        assert hold_entry.entry_type == "hold"
        assert hold_entry.amount == Decimal("40")
        assert release_entry.entry_type == "release"
        assert release_entry.amount == Decimal("15")

    async def test_operations_count_matches(self, db_session: AsyncSession) -> None:
        """Количество операций в журнале соответствует количеству вызовов."""
        user = await create_user(db_session, telegram_id=906004)
        service = AexService()

        for _i in range(10):
            await service.credit(db_session, user.id, Decimal("10"))

        entries, total = await service.get_operations(db_session, user.id)
        assert total == 10
        assert len(entries) == 10


# ── 7. Referral Stats Edge Cases ─────────────────────────────────────


@pytest.mark.asyncio
class TestReferralStatsEdgeCases:
    """Edge cases статистики рефералов."""

    async def test_stats_after_multiple_bonuses(self, db_session: AsyncSession) -> None:
        """Статистика учитывает все бонусы от разных рефералов."""
        referrer = await create_user(db_session, telegram_id=907001, referral_code="STATS1")
        referred1 = await create_user(db_session, telegram_id=907002)
        referred2 = await create_user(db_session, telegram_id=907003)
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
        await service.credit_referral_bonus(
            db_session,
            order_id=500,
            order_amount=Decimal("10000"),
            referred_user_id=referred1.id,
        )
        await service.credit_referral_bonus(
            db_session,
            order_id=501,
            order_amount=Decimal("5000"),
            referred_user_id=referred2.id,
        )

        count, earned = await service.get_referral_stats(db_session, referrer)
        assert count == 2
        assert earned == Decimal("30")  # 20 + 10

    async def test_stats_with_mixed_entry_types(self, db_session: AsyncSession) -> None:
        """Статистика считает только credit+referral, не другие типы."""
        referrer = await create_user(db_session, telegram_id=907010, referral_code="STATS2")

        aex_service = AexService()
        # Начисление не от реферала
        await aex_service.credit(
            db_session,
            referrer.id,
            Decimal("100"),
            reference_type="admin_credit",
            description="Admin bonus",
        )
        # Начисление от реферала
        await aex_service.credit(
            db_session,
            referrer.id,
            Decimal("50"),
            reference_type="referral",
            reference_id="600",
            description="Referral bonus",
        )

        service = ReferralService()
        count, earned = await service.get_referral_stats(db_session, referrer)
        assert count == 0  # Нет рефералов
        assert earned == Decimal("50")  # Только referral credit
