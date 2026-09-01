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
    is_delivery_success,
    reconcile_telegram_write_access,
    send_customer_handoff,
)
from app.services.order_telegram_sync import enqueue_order_telegram_sync_tasks
from app.telegram import messages
from app.telegram.i18n import get_user_translator

logger = logging.getLogger(__name__)
TOKEN_CURRENCY = "ATXG"
_TOKEN_TERMINAL_STATUSES = frozenset({OrderStatus.COMPLETED, OrderStatus.CANCELLED})
_ALLOWED_STATUS_TRANSITIONS = {
    OrderStatus.CREATED: frozenset({OrderStatus.PROCESSING, OrderStatus.CANCELLED}),
    OrderStatus.PROCESSING: frozenset({OrderStatus.COMPLETED, OrderStatus.CANCELLED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}


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
        await telegram_bot.bot.send_message(
            chat_id=referrer.telegram_id,
            text=messages.referral_bonus_reversed(
                amount=amount,
                order_id=order_public_number or order_id,
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
    notify_user: bool = True,
    manager_id: int | None = None,
) -> object:
    try:
        target_status = OrderStatus(int(status))
    except ValueError as exc:
        raise ValueError(f"Unsupported status: {status}") from exc

    repo = OrderRepository(db)
    locked_getter = getattr(repo, "get_one_for_update", None)
    order = (
        await locked_getter(order_id) if callable(locked_getter) else await repo.get_one(order_id)
    )
    if order is None:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)

    validate_order_status_transition(order, target_status, manager_id=manager_id)

    if order.status == int(target_status):
        return order

    if (
        target_status == OrderStatus.PROCESSING
        and manager_id is not None
        and getattr(order, "ManagerId", None) is None
    ):
        order.ManagerId = manager_id

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

    await enqueue_order_telegram_sync_tasks(
        db,
        order_id=order_id,
        status=target_status,
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

    del notify_user
    return hydrated


async def take_order_in_work(
    db: AsyncSession,
    *,
    order_id: int,
    manager: object | None = None,
) -> OrderTakeResult:
    """Перевести заявку в работу и отдельно зафиксировать результат Telegram handoff."""
    if manager is None:
        manager = await UserRepository(db).get_manager()
    manager_id = getattr(manager, "id", None)

    repo = OrderRepository(db)
    locked_getter = getattr(repo, "get_one_for_update", None)
    current = (
        await locked_getter(order_id) if callable(locked_getter) else await repo.get_one(order_id)
    )
    if current is None:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)
    validate_order_status_transition(
        current,
        OrderStatus.PROCESSING,
        manager_id=manager_id,
    )
    if int(current.status) == int(OrderStatus.PROCESSING):
        return OrderTakeResult(order=current, delivery=DeliveryOutcome.SKIPPED)

    order = await update_order_status(
        db,
        order_id=order_id,
        status=OrderStatus.PROCESSING,
        notify_user=False,
        manager_id=manager_id,
    )
    notification_message_id_before = getattr(order, "userNotificationMessageId", None)
    delivery = await send_customer_handoff(order, manager)
    write_access_changed = reconcile_telegram_write_access(
        getattr(order, "user", None),
        delivery,
        operation="customer_handoff",
    )
    notification_message_id = getattr(order, "userNotificationMessageId", None)
    if (
        is_delivery_success(delivery) and notification_message_id != notification_message_id_before
    ) or write_access_changed:
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


def validate_order_status_transition(
    order: object,
    target_status: OrderStatus,
    *,
    manager_id: int | None,
) -> None:
    """Проверить общую матрицу статусов и владельца заявки."""
    current_status = OrderStatus(int(order.status))  # type: ignore[attr-defined]
    assigned_manager_id = getattr(order, "ManagerId", None)
    if (
        manager_id is not None
        and assigned_manager_id is not None
        and int(assigned_manager_id) != int(manager_id)
    ):
        raise AntExException(
            "Order is assigned to another manager",
            code="ORDER_STATUS_CONFLICT",
            status_code=409,
        )
    if current_status == target_status:
        return
    if target_status not in _ALLOWED_STATUS_TRANSITIONS[current_status]:
        raise AntExException(
            "Order status transition is not allowed",
            code="ORDER_STATUS_CONFLICT",
            status_code=409,
        )
    _validate_aex_status_transition(order, target_status)
