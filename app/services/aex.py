"""Сервис AEX — управление кошельками и операциями.
# ruff: noqa: RUF002

All balance operations are atomic: SELECT FOR UPDATE + transaction.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.aex import AexLedgerEntryType
from app.exceptions import AntExException
from app.models.aex import AexLedgerEntry, AexWallet
from app.repositories.aex import AexLedgerEntryRepository, AexWalletRepository


class AexService:
    """Доменный сервис управления AEX-кошельками."""

    async def get_or_create_wallet(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> AexWallet:
        """Получить или создать кошелёк пользователя."""
        repo = AexWalletRepository(db)
        return await repo.get_or_create(user_id)

    async def get_balance(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> AexWallet:
        """Получить баланс кошелька (s blokirovkoy stroki)."""
        wallet = await self._get_wallet_for_update(db, user_id)
        if wallet is None:
            wallet = await AexWalletRepository(db).get_or_create(user_id)
        return wallet

    async def credit(
        self,
        db: AsyncSession,
        user_id: int,
        amount: Decimal,
        *,
        reference_type: str | None = None,
        reference_id: str | None = None,
        description: str | None = None,
    ) -> AexLedgerEntry:
        """Начислить AEX на available-баланс."""
        if amount <= 0:
            raise self._invalid_amount_error()

        wallet = await self._ensure_wallet_for_update(db, user_id)
        wallet.balance_available += amount

        return await self._create_entry(
            db,
            wallet_id=wallet.id,
            amount=amount,
            entry_type=AexLedgerEntryType.CREDIT,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    async def debit(
        self,
        db: AsyncSession,
        user_id: int,
        amount: Decimal,
        *,
        reference_type: str | None = None,
        reference_id: str | None = None,
        description: str | None = None,
    ) -> AexLedgerEntry:
        """Списать AEX s available-баланса."""
        if amount <= 0:
            raise self._invalid_amount_error()

        wallet = await self._ensure_wallet_for_update(db, user_id)
        if wallet.balance_available < amount:
            raise self._insufficient_funds_error()

        wallet.balance_available -= amount

        return await self._create_entry(
            db,
            wallet_id=wallet.id,
            amount=-amount,
            entry_type=AexLedgerEntryType.DEBIT,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    async def hold(
        self,
        db: AsyncSession,
        user_id: int,
        amount: Decimal,
        *,
        reference_type: str | None = None,
        reference_id: str | None = None,
        description: str | None = None,
    ) -> AexLedgerEntry:
        """Заморозить AEX (перевести из available в reserved)."""
        if amount <= 0:
            raise self._invalid_amount_error()

        wallet = await self._ensure_wallet_for_update(db, user_id)
        if wallet.balance_available < amount:
            raise self._insufficient_funds_error()

        wallet.balance_available -= amount
        wallet.balance_reserved += amount

        return await self._create_entry(
            db,
            wallet_id=wallet.id,
            amount=amount,
            entry_type=AexLedgerEntryType.HOLD,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    async def release(
        self,
        db: AsyncSession,
        user_id: int,
        amount: Decimal,
        *,
        reference_type: str | None = None,
        reference_id: str | None = None,
        description: str | None = None,
    ) -> AexLedgerEntry:
        """Разморозить AEX (перевести из reserved в available)."""
        if amount <= 0:
            raise self._invalid_amount_error()

        wallet = await self._ensure_wallet_for_update(db, user_id)
        if wallet.balance_reserved < amount:
            raise self._reserved_exceeds_error()

        wallet.balance_reserved -= amount
        wallet.balance_available += amount

        return await self._create_entry(
            db,
            wallet_id=wallet.id,
            amount=amount,
            entry_type=AexLedgerEntryType.RELEASE,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    async def debit_reserved(
        self,
        db: AsyncSession,
        user_id: int,
        amount: Decimal,
        *,
        reference_type: str | None = None,
        reference_id: str | None = None,
        description: str | None = None,
    ) -> AexLedgerEntry:
        """Списать AEX из reserved-баланса (завершение sale после hold)."""
        if amount <= 0:
            raise self._invalid_amount_error()

        wallet = await self._ensure_wallet_for_update(db, user_id)
        if wallet.balance_reserved < amount:
            raise self._reserved_exceeds_error()

        wallet.balance_reserved -= amount

        return await self._create_entry(
            db,
            wallet_id=wallet.id,
            amount=-amount,
            entry_type=AexLedgerEntryType.DEBIT,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    async def get_operations(
        self,
        db: AsyncSession,
        user_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AexLedgerEntry], int]:
        """Получить историю операций пользователя (offset pagination)."""
        wallet = await AexWalletRepository(db).get_by_user_id(user_id)
        if wallet is None:
            return [], 0

        entry_repo = AexLedgerEntryRepository(db)
        entries = await entry_repo.get_by_wallet(wallet.id, limit=limit, offset=offset)
        total = await entry_repo.count_by_wallet(wallet.id)
        return entries, total

    async def get_operations_cursor(
        self,
        db: AsyncSession,
        user_id: int,
        *,
        limit: int = 50,
        cursor: int | None = None,
    ) -> tuple[list[AexLedgerEntry], int | None]:
        """Получить историю операций (cursor pagination).

        Returns:
            (entries, next_cursor) — next_cursor=None если страниц больше нет.
        """
        wallet = await AexWalletRepository(db).get_by_user_id(user_id)
        if wallet is None:
            return [], None

        entry_repo = AexLedgerEntryRepository(db)
        rows = await entry_repo.get_by_wallet_cursor(
            wallet.id, limit=limit, cursor=cursor
        )
        # Detect has_more: if we got limit+1, there's a next page
        next_cursor: int | None = None
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        if rows:
            next_cursor = rows[-1].id if has_more else None
        return rows, next_cursor

    async def _get_wallet_for_update(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> AexWallet | None:
        """Получить кошелёк po SELECT FOR UPDATE."""
        result = await db.execute(
            select(AexWallet).where(AexWallet.user_id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def _ensure_wallet_for_update(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> AexWallet:
        """Получить или создать кошелёк s blokirovkoy."""
        wallet = await self._get_wallet_for_update(db, user_id)
        if wallet is None:
            repo = AexWalletRepository(db)
            await repo.create(
                user_id=user_id,
                balance_available=Decimal("0"),
                balance_reserved=Decimal("0"),
            )
            # Re-fetch with FOR UPDATE
            wallet = await self._get_wallet_for_update(db, user_id)
            if wallet is None:
                raise AntExException(
                    "Failed to create wallet",
                    code="WALLET_CREATE_FAILED",
                    status_code=500,
                )
        return wallet

    async def _create_entry(
        self,
        db: AsyncSession,
        *,
        wallet_id: int,
        amount: Decimal,
        entry_type: AexLedgerEntryType,
        reference_type: str | None,
        reference_id: str | None,
        description: str | None,
    ) -> AexLedgerEntry:
        """Создать запись в журнале."""
        repo = AexLedgerEntryRepository(db)
        return await repo.create(
            wallet_id=wallet_id,
            amount=amount,
            entry_type=entry_type.value,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    @staticmethod
    def _invalid_amount_error() -> AntExException:
        return AntExException(
            "Amount must be positive",
            code="INVALID_AMOUNT",
            status_code=422,
        )

    @staticmethod
    def _insufficient_funds_error() -> AntExException:
        return AntExException(
            "Insufficient AEX balance",
            code="INSUFFICIENT_FUNDS",
            status_code=422,
        )

    @staticmethod
    def _reserved_exceeds_error() -> AntExException:
        return AntExException(
            "Reserved balance insufficient for release",
            code="RESERVED_EXCEEDS",
            status_code=422,
        )
