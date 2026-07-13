# ruff: noqa: RUF002
"""Сервис реферальной системы.

Генерация referral-кода, валидация deep-link, связывание пользователей,
начисление ATXG за обмены рефералов.
"""

from __future__ import annotations

import logging
import secrets
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AntExException
from app.models.aex import AexLedgerEntry
from app.models.user import User
from app.repositories.rate import RateRepository
from app.repositories.user import UserRepository
from app.services.aex_rate import ATXG_RATE_QUANTIZER
from app.telegram import messages
from app.telegram.i18n import get_user_translator

logger = logging.getLogger(__name__)

REFERRAL_CODE_LENGTH = 8
DEFAULT_REFERRAL_BOT_USERNAME = "antex_bot"
INVALID_REFERRAL_CODE_MESSAGE = "Неверный реферальный код. Проверте или удалите!"


def build_referral_link(referral_code: str, bot_username: str | None = None) -> str:
    """Собрать готовую Telegram Mini App deep-link ссылку по referral-коду."""
    username = (bot_username or DEFAULT_REFERRAL_BOT_USERNAME).strip().lstrip("@")
    if not username:
        username = DEFAULT_REFERRAL_BOT_USERNAME
    return f"https://t.me/{username}?startapp=ref_{referral_code}"


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
        - Нельзя менять уже установленную пользовательскую привязку
        - Код должен существовать
        """
        if user.referred_by is not None:
            return user

        repo = UserRepository(db)
        self._validate_referral_code(referral_code)
        referrer = await repo.get_by_referral_code(referral_code)

        if referrer is None:
            raise self._invalid_referral_code_error()

        if referrer.id == user.id:
            raise AntExException(
                "Cannot refer yourself",
                code="SELF_REFERRAL",
                status_code=422,
            )

        if referrer.referred_by == user.id:
            raise AntExException(
                "Cannot create mutual referral",
                code="MUTUAL_REFERRAL",
                status_code=422,
            )

        await repo.update(user, referred_by=referrer.id)
        await db.refresh(user)
        return user

    async def set_referrer_by_code(
        self,
        db: AsyncSession,
        user: User,
        referral_code: str | None,
    ) -> User:
        """Admin-only смена привязки реферера с теми же доменными запретами."""
        repo = UserRepository(db)
        if referral_code is None or referral_code == "":
            await repo.update(user, referred_by=None)
            await db.refresh(user)
            return user

        self._validate_referral_code(referral_code)
        referrer = await repo.get_by_referral_code(referral_code)
        if referrer is None:
            raise self._invalid_referral_code_error()

        if referrer.id == user.id:
            raise AntExException(
                "Cannot refer yourself",
                code="SELF_REFERRAL",
                status_code=422,
            )

        if referrer.referred_by == user.id:
            raise AntExException(
                "Cannot create mutual referral",
                code="MUTUAL_REFERRAL",
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
        """Получить статистику рефералов: (количество, общий заработок ATXG)."""
        repo = UserRepository(db)
        total_referrals = await repo.count_referrals(user.id)

        # Подсчитать общий заработок через ATXG ledger
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

    async def get_referral_earnings_by_user_id(
        self,
        db: AsyncSession,
        user: User,
        referral_user_ids: list[int],
    ) -> dict[int, Decimal]:
        """Вернуть сумму ATXG-начислений по каждому приглашённому пользователю."""
        if not referral_user_ids:
            return {}

        from sqlalchemy import String, cast, func, select

        from app.models.aex import AexLedgerEntry
        from app.models.order import Order
        from app.repositories.aex import AexWalletRepository

        wallet = await AexWalletRepository(db).get_by_user_id(user.id)
        if wallet is None:
            return {}

        result = await db.execute(
            select(Order.UserId, func.sum(AexLedgerEntry.amount))
            .join(AexLedgerEntry, AexLedgerEntry.reference_id == cast(Order.id, String))
            .where(
                AexLedgerEntry.wallet_id == wallet.id,
                AexLedgerEntry.entry_type == "credit",
                AexLedgerEntry.reference_type == "referral",
                Order.UserId.in_(referral_user_ids),
            )
            .group_by(Order.UserId)
        )
        return {user_id: amount or Decimal("0") for user_id, amount in result.all()}

    async def credit_referral_bonus(
        self,
        db: AsyncSession,
        *,
        order_id: int,
        order_amount: Decimal,
        referred_user_id: int,
        currency_sell: str = "USDT",
        currency_buy: str | None = None,
    ) -> Decimal:
        """Начислить ATXG пригласившему за обмен реферала.

        Возвращает начисленную сумму ATXG.
        `order_amount` передаётся в валюте продажи заявки.
        """
        user_repo = UserRepository(db)
        referred_user = await user_repo.get_one(referred_user_id)
        if referred_user is None or referred_user.referred_by is None:
            return Decimal("0")

        referrer_id = referred_user.referred_by
        existing_entry = await self._get_referral_bonus_entry(db, order_id)
        if existing_entry is not None:
            return existing_entry.amount

        # Получить эффективную ставку
        from app.services.aex_rate import AexRateService

        rate_service = AexRateService()
        rate = await rate_service.get_effective_rate(db, referrer_id)
        aex_base_amount = await self._convert_order_amount_to_aex_base(
            db,
            order_amount=order_amount,
            currency_sell=currency_sell,
            currency_buy=currency_buy,
        )
        aex_amount = (aex_base_amount * rate).quantize(ATXG_RATE_QUANTIZER)

        if aex_amount <= 0:
            return Decimal("0")

        # Начислить ATXG
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
        await self._notify_referral_bonus(
            db,
            referrer_id=referrer_id,
            order_id=order_id,
            amount=aex_amount,
        )

        logger.info(
            "Credited %s ATXG to user %s for referral order %s (rate=%s base=%s %s)",
            aex_amount,
            referrer_id,
            order_id,
            rate,
            aex_base_amount,
            currency_sell.upper(),
        )
        return aex_amount

    async def generate_batch_referral_codes(
        self,
        db: AsyncSession,
    ) -> int:
        """Сгенерировать реферальные коды для всех пользователей без кода.

        Возвращает количество сгенерированных кодов.
        """
        repo = UserRepository(db)
        users = await repo.get_users_without_referral_code()

        if not users:
            return 0

        generated = 0
        for user in users:
            code = await self._generate_unique_code(db)
            await repo.update(user, referral_code=code)
            generated += 1

        logger.info("Batch generated %d referral codes", generated)
        return generated

    async def generate_referral_code_for_user(
        self,
        db: AsyncSession,
        user: User,
        *,
        regenerate: bool = False,
    ) -> str:
        """Создать или вручную пересоздать referral_code выбранного пользователя."""
        if user.referral_code and not regenerate:
            return user.referral_code

        repo = UserRepository(db)
        code = await self._generate_unique_code(db)
        await repo.update(user, referral_code=code)
        await db.refresh(user)
        return code

    async def _generate_unique_code(self, db: AsyncSession) -> str:
        """Сгенерировать уникальный реферальный код."""
        repo = UserRepository(db)
        for _ in range(10):
            code = secrets.token_urlsafe(REFERRAL_CODE_LENGTH)[:REFERRAL_CODE_LENGTH]
            if not code.isascii() or not code.isalnum():
                continue
            existing = await repo.get_by_referral_code(code)
            if existing is None:
                return code
        raise AntExException(
            "Failed to generate unique referral code",
            code="CODE_GENERATION_FAILED",
            status_code=500,
        )

    def _validate_referral_code(self, referral_code: str) -> None:
        """Проверить публичный referral-код из deep-link/admin формы."""
        if (
            len(referral_code) != REFERRAL_CODE_LENGTH
            or not referral_code.isascii()
            or not referral_code.isalnum()
        ):
            raise self._invalid_referral_code_error()

    def _invalid_referral_code_error(self) -> AntExException:
        """Единая ошибка для неверного формата и несуществующего кода."""
        return AntExException(
            INVALID_REFERRAL_CODE_MESSAGE,
            code="INVALID_REFERRAL_CODE",
            status_code=422,
        )

    async def _get_referral_bonus_entry(
        self,
        db: AsyncSession,
        order_id: int,
    ) -> AexLedgerEntry | None:
        """Найти уже созданное referral-начисление по заявке."""
        result = await db.execute(
            select(AexLedgerEntry).where(
                AexLedgerEntry.reference_type == "referral",
                AexLedgerEntry.reference_id == str(order_id),
                AexLedgerEntry.entry_type == "credit",
            )
        )
        return result.scalar_one_or_none()

    async def _convert_order_amount_to_aex_base(
        self,
        db: AsyncSession,
        *,
        order_amount: Decimal,
        currency_sell: str,
        currency_buy: str | None,
    ) -> Decimal:
        """Привести сумму заявки к USDT-базе, от которой начисляется ATXG."""
        if order_amount <= 0:
            return Decimal("0")

        sell = currency_sell.upper()
        if sell == "USDT":
            return order_amount.quantize(ATXG_RATE_QUANTIZER)

        if sell != "RUB":
            raise AntExException(
                f"Unsupported sell currency for referral bonus: {sell}",
                code="UNSUPPORTED_REFERRAL_BONUS_CURRENCY",
                status_code=422,
            )

        if not currency_buy:
            raise AntExException(
                "Currency buy is required for RUB referral bonus conversion",
                code="REFERRAL_BONUS_CONTEXT_MISSING",
                status_code=500,
            )

        buy = currency_buy.upper()
        rate_repo = RateRepository(db)
        rub_pair = await rate_repo.find_by_currency(f"RUB{buy}")
        usdt_pair = await rate_repo.find_by_currency(f"USDT{buy}")

        if rub_pair is None or usdt_pair is None or rub_pair.price <= 0 or usdt_pair.price <= 0:
            raise AntExException(
                f"Missing conversion rates for referral bonus base: RUB{buy}/USDT{buy}",
                code="REFERRAL_BONUS_RATE_UNAVAILABLE",
                status_code=409,
            )

        usdt_rub = Decimal(str(usdt_pair.price)) / Decimal(str(rub_pair.price))
        return (order_amount / usdt_rub).quantize(ATXG_RATE_QUANTIZER)

    async def _notify_referral_bonus(
        self,
        db: AsyncSession,
        *,
        referrer_id: int,
        order_id: int,
        amount: Decimal,
    ) -> None:
        """Best-effort Telegram-уведомление рефереру после начисления."""
        referrer = await UserRepository(db).get_one(referrer_id)
        if referrer is None or not referrer.telegram_id:
            return

        from app.telegram import bot as telegram_bot

        if telegram_bot.bot is None:
            logger.warning("Referral bonus notification skipped: bot is not initialized")
            return

        try:
            translate = get_user_translator(referrer)
            await telegram_bot.bot.send_message(
                chat_id=referrer.telegram_id,
                text=messages.referral_bonus_credited(
                    amount=amount,
                    order_id=order_id,
                    translator=translate,
                ),
            )
        except Exception:
            logger.exception(
                "Failed to send referral bonus notification: referrer_id=%s order_id=%s",
                referrer_id,
                order_id,
            )
