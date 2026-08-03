"""Единый сервис смены статуса заявки."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.order import OrderStatus
from app.exceptions import AntExException
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.services.order_notifications import (
    DeliveryOutcome,
    build_chat_url_for_user,
    notify_order_status_changed,
    send_customer_handoff,
)
from app.telegram import messages
from app.telegram.i18n import get_user_translator
from app.telegram.presentation.delivery import DeliveryKind, deliver

logger = logging.getLogger(__name__)
TOKEN_CURRENCY = "ATXG"
_TOKEN_TERMINAL_STATUSES = frozenset({OrderStatus.COMPLETED, OrderStatus.CANCELLED})


@dataclass(frozen=True)
class OrderTakeResult:
    order: object
    delivery: DeliveryOutcome


async def _notify_referral_reversal(
    db: AsyncSession,
    *,
    referrer_id: int,
    order_id: int,
    order_public_number: int | str | None = None,
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
        outcome = await deliver(
            telegram_bot.bot,
            chat_id=referrer.telegram_id,
            spec=messages.referral_bonus_message(
                amount=amount,
                order_id=order_public_number or order_id,
                reversed=True,
                translator=translate,
            ),
            kind=DeliveryKind.SEND,
        )
        if not outcome.delivered:
            raise outcome.error or RuntimeError("Referral reversal notification was not delivered")
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
    notify_user: bool = True,
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

    _validate_aex_status_transition(order, target_status)

    order = await repo.update_status(order_id, int(target_status))
    hydrated = await repo.get_one(order_id)
    if hydrated is None:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)

    if target_status == OrderStatus.COMPLETED:
        order_amount = Decimal(str(hydrated.amountSell))
        if _is_aex_withdrawal_order(hydrated):
            from app.services.aex import AexService

            await AexService().debit_order_withdrawal(
                db,
                hydrated.UserId,
                order_amount,
                order_id=hydrated.id,
            )
        else:
            from app.services.referral import ReferralService

            referral_service = ReferralService()
            await referral_service.credit_referral_bonus(
                db,
                order_id=hydrated.id,
                order_public_number=getattr(hydrated, "publicNumber", hydrated.id),
                order_amount=order_amount,
                referred_user_id=hydrated.UserId,
                currency_sell=str(hydrated.currencySell),
                currency_buy=str(hydrated.currencyBuy),
            )

    if target_status == OrderStatus.CANCELLED and _is_aex_withdrawal_order(hydrated):
        from app.services.aex import AexService

        await AexService().release_order_withdrawal(
            db,
            hydrated.UserId,
            Decimal(str(hydrated.amountSell)),
            order_id=hydrated.id,
        )

    await db.commit()

    if target_status == OrderStatus.CANCELLED and not _is_aex_withdrawal_order(hydrated):
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
                            "Reversed %s ATXG from user %s for cancelled order %s",
                            referral_entry.amount,
                            wallet.user_id,
                            order_id,
                        )
                        await _notify_referral_reversal(
                            db,
                            referrer_id=wallet.user_id,
                            order_id=order_id,
                            order_public_number=getattr(
                                hydrated,
                                "publicNumber",
                                order_id,
                            ),
                            amount=referral_entry.amount,
                        )
                    else:
                        logger.warning(
                            "Insufficient ATXG balance for reversal:"
                            " user=%s has=%s needs=%s order=%s",
                            wallet.user_id,
                            wallet.balance_available,
                            referral_entry.amount,
                            order_id,
                        )
        except Exception:
            logger.exception(
                "Failed to reverse ATXG referral bonus for cancelled order_id=%s",
                order_id,
            )

    if not notify_user:
        return hydrated

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


async def take_order_in_work(db: AsyncSession, *, order_id: int) -> OrderTakeResult:
    """Перевести заявку в работу и отдельно зафиксировать результат Telegram handoff."""
    current = await OrderRepository(db).get_one(order_id)
    if current is None:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)
    if int(current.status) != int(OrderStatus.CREATED):
        raise AntExException(
            "Order is no longer available for taking",
            code="ORDER_STATUS_CONFLICT",
            status_code=409,
        )

    order = await update_order_status(
        db,
        order_id=order_id,
        status=OrderStatus.PROCESSING,
        notify_user=False,
    )
    manager = await UserRepository(db).get_manager()
    notification_message_id_before = getattr(order, "userNotificationMessageId", None)
    delivery = await send_customer_handoff(order, manager)
    notification_message_id = getattr(order, "userNotificationMessageId", None)
    if (
        delivery != DeliveryOutcome.FAILED
        and notification_message_id != notification_message_id_before
    ):
        try:
            await db.commit()
        except SQLAlchemyError:
            await db.rollback()
            logger.exception(
                "Failed to persist handoff message id: order_id=%s message_id=%s",
                order_id,
                notification_message_id,
            )
            reloaded = await OrderRepository(db).get_one(order_id)
            if reloaded is not None:
                order = reloaded
    return OrderTakeResult(order=order, delivery=delivery)


def _is_aex_withdrawal_order(order: object) -> bool:
    """Проверить, что заявка расходует внутренний токен."""
    return str(getattr(order, "currencySell", "")).upper() == TOKEN_CURRENCY


def _validate_aex_status_transition(order: object, target_status: OrderStatus) -> None:
    """Запретить смену финального ATXG-статуса без отдельной компенсационной операции."""
    if not _is_aex_withdrawal_order(order):
        return

    current_status = OrderStatus(int(order.status))
    if current_status in _TOKEN_TERMINAL_STATUSES:
        raise AntExException(
            "ATXG order final status cannot be changed",
            code="ATXG_ORDER_FINAL_STATUS_LOCKED",
            status_code=422,
        )
