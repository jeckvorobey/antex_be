"""Постановка и выполнение заданий Telegram-синхронизации заявки."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.enums.order import OrderStatus
from app.models.order_telegram_sync_task import OrderTelegramSyncTask
from app.repositories.order import OrderRepository
from app.repositories.order_telegram_sync_task import OrderTelegramSyncTaskRepository
from app.services.order_notifications import (
    DeliveryOutcome,
    build_manager_status_markup,
    build_manager_status_text,
    is_permanent_telegram_delivery_error,
    notify_order_status_changed,
    reconcile_telegram_write_access,
)

logger = logging.getLogger(__name__)
SYNC_TARGETS = ("user", "manager")


class SyncResult(StrEnum):
    DELIVERED = "delivered"
    RETRY = "retry"
    FAILED = "failed"


async def enqueue_order_telegram_sync_tasks(
    db: AsyncSession,
    *,
    order_id: int,
    status: OrderStatus | int,
) -> None:
    repo = OrderTelegramSyncTaskRepository(db)
    for target in SYNC_TARGETS:
        await repo.enqueue(order_id=order_id, status=int(status), target=target)


def _is_not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in str(exc).lower()


async def _deliver_manager(
    order: object,
    *,
    customer_notified: bool = True,
) -> tuple[SyncResult, str | None]:
    chat_id = getattr(order, "managerNotificationChatId", None)
    message_id = getattr(order, "managerNotificationMessageId", None)
    if chat_id is None or message_id is None:
        return SyncResult.RETRY, "message_link_missing"
    from app.telegram import bot as telegram_bot

    if telegram_bot.bot is None:
        return SyncResult.RETRY, "bot_unavailable"
    try:
        await telegram_bot.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_manager_status_text(order, customer_notified=customer_notified),
            reply_markup=build_manager_status_markup(order),
        )
    except TelegramBadRequest as exc:
        if _is_not_modified(exc):
            return SyncResult.DELIVERED, None
        if "message to edit not found" in str(exc).lower():
            try:
                replacement = await telegram_bot.bot.send_message(
                    chat_id=chat_id,
                    text=build_manager_status_text(order, customer_notified=customer_notified),
                    reply_markup=build_manager_status_markup(order),
                )
            except Exception:
                logger.exception(
                    "Manager Telegram replacement failed: order_id=%s",
                    getattr(order, "id", None),
                )
                return SyncResult.RETRY, "telegram_temporary_error"
            order.managerNotificationMessageId = replacement.message_id
            return SyncResult.DELIVERED, None
        if is_permanent_telegram_delivery_error(exc):
            return SyncResult.FAILED, "chat_inaccessible"
        return SyncResult.RETRY, "telegram_bad_request"
    except (TelegramForbiddenError, TelegramNotFound):
        return SyncResult.FAILED, "chat_inaccessible"
    except Exception:
        logger.exception("Manager Telegram sync failed: order_id=%s", getattr(order, "id", None))
        return SyncResult.RETRY, "telegram_temporary_error"
    return SyncResult.DELIVERED, None


async def _deliver_user(
    order: object,
) -> tuple[SyncResult, str | None]:
    outcome = await notify_order_status_changed(order)
    reconcile_telegram_write_access(
        getattr(order, "user", None),
        outcome,
        operation="order_status_sync",
    )
    if outcome in {DeliveryOutcome.RICH, DeliveryOutcome.FALLBACK, DeliveryOutcome.SENT}:
        return SyncResult.DELIVERED, None
    if outcome == DeliveryOutcome.INACCESSIBLE:
        return SyncResult.FAILED, "chat_inaccessible"
    return SyncResult.RETRY, "telegram_temporary_error"


async def process_order_telegram_sync_task(
    db: AsyncSession,
    task,
) -> None:
    order = await OrderRepository(db).get_one(task.OrderId)
    now = datetime.now(UTC)
    if order is None:
        task.state = "failed"
        task.lastErrorCode = "order_not_found"
        task.lockedAt = None
        return
    if int(order.status) != int(task.status):
        task.state = "delivered"
        task.deliveredAt = now
        task.lastErrorCode = "stale_status"
        task.lockedAt = None
        return

    if task.target == "user":
        result, error_code = await _deliver_user(order)
    else:
        customer_notified = True
        if int(task.status) == int(OrderStatus.PROCESSING):
            user_task = await db.scalar(
                select(OrderTelegramSyncTask).where(
                    OrderTelegramSyncTask.OrderId == task.OrderId,
                    OrderTelegramSyncTask.status == task.status,
                    OrderTelegramSyncTask.target == "user",
                )
            )
            if user_task is not None and user_task.state not in {"delivered", "failed"}:
                result, error_code = SyncResult.RETRY, "user_delivery_pending"
            else:
                customer_notified = user_task is None or user_task.state == "delivered"
                result, error_code = await _deliver_manager(
                    order,
                    customer_notified=customer_notified,
                )
        else:
            result, error_code = await _deliver_manager(order)
    task.attemptCount += 1
    task.lastErrorCode = error_code
    task.lockedAt = None
    if result == SyncResult.DELIVERED:
        task.state = "delivered"
        task.deliveredAt = now
    elif (
        result == SyncResult.FAILED
        or task.attemptCount >= settings.order_telegram_sync_max_attempts
    ):
        task.state = "failed"
    else:
        task.state = "retry"
        delay = settings.order_telegram_sync_retry_base_seconds * 2 ** (task.attemptCount - 1)
        task.nextAttemptAt = now + timedelta(seconds=delay)


async def process_order_telegram_sync_batch() -> int:
    from app.core.database import async_session

    processed = 0
    for _ in range(settings.order_telegram_sync_batch_size):
        async with async_session() as db:
            tasks = await OrderTelegramSyncTaskRepository(db).claim_due(
                limit=1,
                lease_seconds=settings.order_telegram_sync_lease_seconds,
            )
            await db.commit()
        if not tasks:
            break
        task = tasks[0]
        async with async_session() as db:
            persisted = await db.get(type(task), task.id)
            if persisted is None:
                continue
            try:
                await process_order_telegram_sync_task(db, persisted)
            except Exception:
                logger.exception("Order Telegram sync task failed: task_id=%s", persisted.id)
                persisted.attemptCount += 1
                persisted.lockedAt = None
                persisted.lastErrorCode = "unexpected_error"
                if persisted.attemptCount >= settings.order_telegram_sync_max_attempts:
                    persisted.state = "failed"
                else:
                    persisted.state = "retry"
                    delay = settings.order_telegram_sync_retry_base_seconds * 2 ** (
                        persisted.attemptCount - 1
                    )
                    persisted.nextAttemptAt = datetime.now(UTC) + timedelta(seconds=delay)
            await db.commit()
        processed += 1
    return processed


async def order_telegram_sync_loop() -> None:
    while True:
        try:
            processed = await process_order_telegram_sync_batch()
        except Exception:
            logger.exception("Order Telegram sync batch failed")
            processed = 0
        if processed == 0:
            await asyncio.sleep(settings.order_telegram_sync_poll_seconds)
