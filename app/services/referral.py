"""Сервис реферальной системы.

Генерация referral-кода, валидация deep-link, связывание пользователей,
начисление AEX за обмены рефералов.
"""

from __future__ import annotations

import logging
import secrets
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AntExException
from app.models.user import User
from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)

REFERRAL_CODE_LENGTH = 8
REFERRAL_RATE_DEFAULT = Decimal("0.002")


class ReferralService:
    """Доменный сервис реферальной системы."""

    async def get_or_create_referral_code(
        self,
        db: AsyncSession,
        user: User,
    ) -> str:
        """Получить или сгенерировать реферальный код пользователя."""
        if user.referral_code:
            return user.referral_code

        repo = UserRepository(db)
        code = await self._generate_unique_code(db)
        await repo.update(user, referral_code=code)
        await db.refresh(user)
        return code

    async def bind_referral(
        self,
        db: AsyncSession,
        user: User,
        referral_code: str,
    ) -> User:
        """Привязать пользователя к рефералу по коду.

        Правила:
        - Нельзя привязать себя
        - Нельзя привязать повторно
        - Код должен существовать
        """
        if user.referred_by is not None:
            raise AntExException(
                "User already has a referrer",
                code="ALREADY_REFERRED",
                status_code=422,
            )

        repo = UserRepository(db)
        referrer = await repo.get_by_referral_code(referral_code)

        if referrer is None:
            raise AntExException(
                "Invalid referral code",
                code="INVALID_REFERRAL_CODE",
                status_code=422,
            )

        if referrer.id == user.id:
            raise AntExException(
                "Cannot refer yourself",
                code="SELF_REFERRAL",
                status_code=422,
            )

        await repo.update(user, referred_by=referrer.id)
        await db.refresh(user)
        return user

    async def get_referral_list(
        self,
        db: AsyncSession,
        user: User,
    ) -> list[User]:
        """Получить список рефералов пользователя."""
        repo = UserRepository(db)
        return await repo.get_referrals(user.id)

    async def get_referral_stats(
        self,
        db: AsyncSession,
        user: User,
    ) -> tuple[int, Decimal]:
        """Получить статистику рефералов: (количество, общий заработок AEX)."""
        repo = UserRepository(db)
        total_referrals = await repo.count_referrals(user.id)

        # Подсчитать общий заработок через AEX ledger
        from app.repositories.aex import AexWalletRepository

        wallet = await AexWalletRepository(db).get_by_user_id(user.id)
        if wallet is None:
            return total_referrals, Decimal("0")

        # Сумма всех referral credit-записей
        from sqlalchemy import func, select

        from app.models.aex import AexLedgerEntry

        result = await db.execute(
            select(func.sum(AexLedgerEntry.amount)).where(
                AexLedgerEntry.wallet_id == wallet.id,
                AexLedgerEntry.entry_type == "credit",
                AexLedgerEntry.reference_type == "referral",
            )
        )
        total_earned = result.scalar() or Decimal("0")

        return total_referrals, total_earned

    async def credit_referral_bonus(
        self,
        db: AsyncSession,
        *,
        order_id: int,
        order_amount: Decimal,
        referred_user_id: int,
    ) -> Decimal:
        """Начислить AEX пригласившему за обмен реферала.

        Возвращает начисленную сумму AEX.
        Esli u referala net priglashennogo - nichego ne delaet.
        """
        user_repo = UserRepository(db)
        referred_user = await user_repo.get_one(referred_user_id)
        if referred_user is None or referred_user.referred_by is None:
            return Decimal("0")

        referrer_id = referred_user.referred_by

        # Получить эффективную ставку
        from app.services.aex_rate import AexRateService

        rate_service = AexRateService()
        rate = await rate_service.get_effective_rate(db, referrer_id)
        aex_amount = (order_amount * rate).quantize(Decimal("0.000001"))

        if aex_amount <= 0:
            return Decimal("0")

        # Начислить AEX
        from app.services.aex import AexService

        aex_service = AexService()
        await aex_service.credit(
            db,
            referrer_id,
            aex_amount,
            reference_type="referral",
            reference_id=str(order_id),
            description=f"Referral bonus for order #{order_id}",
        )

        logger.info(
            "Credited %s AEX to user %s for referral order %s (rate=%s)",
            aex_amount,
            referrer_id,
            order_id,
            rate,
        )
        return aex_amount

    async def _generate_unique_code(self, db: AsyncSession) -> str:
        """Сгенерировать уникальный реферальный код."""
        repo = UserRepository(db)
        for _ in range(10):
            code = secrets.token_urlsafe(REFERRAL_CODE_LENGTH)[:REFERRAL_CODE_LENGTH]
            existing = await repo.get_by_referral_code(code)
            if existing is None:
                return code
        raise AntExException(
            "Failed to generate unique referral code",
            code="CODE_GENERATION_FAILED",
            status_code=500,
        )
