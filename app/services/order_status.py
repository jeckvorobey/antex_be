"""Единый сервис смены статуса заявки."""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.order import OrderStatus
from app.exceptions import AntExException
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.services.order_notifications import (
    build_chat_url_for_user,
    notify_order_status_changed,
)
from app.telegram import messages
from app.telegram.i18n import get_user_translator

logger = logging.getLogger(__name__)


async def _notify_referral_reversal(
    db: AsyncSession,
    *,
    referrer_id: int,
    order_id: int,
    amount: Decimal,
) -> None:
    """Best-effort Telegram notification for referral bonus reversal."""
    referrer = await UserRepository(db).get_one(referrer_id)
    if referrer is None or not referrer.telegram_id:
        return

    from app.telegram import bot as telegram_bot

    if telegram_bot.bot is None:
        logger.warning("Referral reversal notification skipped: bot is not initialized")
        return

    try:
        translate = get_user_translator(referrer)
        await telegram_bot.bot.send_message(
            chat_id=referrer.telegram_id,
            text=messages.referral_bonus_reversed(
                amount=amount,
                order_id=order_id,
                translator=translate,
            ),
        )
    except Exception:
        logger.exception(
            "Failed to send referral bonus reversal notification: referrer_id=%s order_id=%s",
            referrer_id,
            order_id,
        )


async def update_order_status(
    db: AsyncSession,
    *,
    order_id: int,
    status: OrderStatus | int,
) -> object:
    try:
        target_status = OrderStatus(int(status))
    except ValueError as exc:
        raise ValueError(f"Unsupported status: {status}") from exc

    repo = OrderRepository(db)
    order = await repo.get_one(order_id)
    if order is None:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)

    if order.status == int(target_status):
        return order

    order = await repo.update_status(order_id, int(target_status))
    hydrated = await repo.get_one(order_id)
    if hydrated is None:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)

    # Начислить AEX рефереру при завершении обмена
    if target_status == OrderStatus.COMPLETED:
        from decimal import Decimal

        from app.services.referral import ReferralService

        referral_service = ReferralService()
        order_amount = Decimal(str(hydrated.amountSell))
        await referral_service.credit_referral_bonus(
            db,
            order_id=hydrated.id,
            order_amount=order_amount,
            referred_user_id=hydrated.UserId,
            currency_sell=str(hydrated.currencySell),
            currency_buy=str(hydrated.currencyBuy),
        )

    await db.commit()

    # Списать AEX рефереру при отмене обмена (компенсация)
    if target_status == OrderStatus.CANCELLED:
        try:
            from sqlalchemy import select

            from app.models.aex import AexLedgerEntry
            from app.services.aex import AexService

            # Найти начисление referral за этот заказ
            referral_result = await db.execute(
                select(AexLedgerEntry).where(
                    AexLedgerEntry.reference_type == "referral",
                    AexLedgerEntry.reference_id == str(order_id),
                    AexLedgerEntry.entry_type == "credit",
                )
            )
            referral_entry = referral_result.scalar_one_or_none()

            if referral_entry is not None:
                # Найти владельца кошелька
                from app.repositories.aex import AexWalletRepository

                wallet = await AexWalletRepository(db).get_by_id(referral_entry.wallet_id)
                if wallet is not None:
                    aex_service = AexService()
                    # Проверить достаточность баланса перед списанием
                    if wallet.balance_available >= referral_entry.amount:
                        await aex_service.debit(
                            db,
                            wallet.user_id,
                            referral_entry.amount,
                            reference_type="referral_reversal",
                            reference_id=str(order_id),
                            description=f"Referral bonus reversal for cancelled order #{order_id}",
                        )
                        await db.commit()
                        logger.info(
                            "Reversed %s AEX from user %s for cancelled order %s",
                            referral_entry.amount,
                            wallet.user_id,
                            order_id,
                        )
                        await _notify_referral_reversal(
                            db,
                            referrer_id=wallet.user_id,
                            order_id=order_id,
                            amount=referral_entry.amount,
                        )
                    else:
                        logger.warning(
                            "Insufficient AEX balance for reversal:"
                            " user=%s has=%s needs=%s order=%s",
                            wallet.user_id,
                            wallet.balance_available,
                            referral_entry.amount,
                            order_id,
                        )
        except Exception:
            logger.exception(
                "Failed to reverse AEX referral bonus for cancelled order_id=%s",
                order_id,
            )

    manager = await UserRepository(db).get_manager()
    manager_chat_url = build_chat_url_for_user(manager) if manager is not None else None

    try:
        await notify_order_status_changed(hydrated, manager_chat_url=manager_chat_url)
        await db.commit()
    except Exception:
        logger.exception(
            "Failed to send order status notification for order_id=%s status=%s",
            order_id,
            int(target_status),
        )
        await db.rollback()
    return hydrated
