"""Фоновый runner рассылок."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from html import escape
from typing import Any

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import async_session
from app.modules.broadcasts.audience import BroadcastRecipient, TelegramUserAudienceProvider
from app.modules.broadcasts.repository import BroadcastRepository

DEFAULT_PROGRESS_BATCH_SIZE = 10
_active_tasks: dict[int, asyncio.Task[None]] = {}


class BroadcastDeliveryError(RuntimeError):
    def __init__(self, message: str, *, success_count: int, failed_count: int) -> None:
        super().__init__(message)
        self.success_count = success_count
        self.failed_count = failed_count


class BroadcastRateLimiter:
    def __init__(self, target_rps: int) -> None:
        self.interval = 1 / max(target_rps, 1)
        self._lock = asyncio.Lock()
        self._next_slot = 0.0
        self._pause_until = 0.0

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            delay = 0.0
            async with self._lock:
                now = loop.time()
                if self._pause_until > now:
                    delay = self._pause_until - now
                else:
                    slot = max(now, self._next_slot)
                    delay = max(slot - now, 0.0)
                    self._next_slot = slot + self.interval

            if delay <= 0:
                return
            await asyncio.sleep(delay)

    async def pause(self, seconds: float) -> None:
        loop = asyncio.get_running_loop()
        async with self._lock:
            pause_until = loop.time() + seconds
            self._pause_until = max(self._pause_until, pause_until)
            self._next_slot = max(self._next_slot, self._pause_until)


def normalize_text(text: str, text_format: str) -> str:
    if text_format == "html":
        return text
    return escape(text)


async def schedule_broadcast(*, broadcast_id: int) -> None:
    if broadcast_id in _active_tasks and not _active_tasks[broadcast_id].done():
        return

    task = asyncio.create_task(
        run_broadcast(broadcast_id=broadcast_id),
        name=f"broadcast-{broadcast_id}",
    )
    _active_tasks[broadcast_id] = task

    def _cleanup(done_task: asyncio.Task[None]) -> None:
        del done_task
        _active_tasks.pop(broadcast_id, None)

    task.add_done_callback(_cleanup)


async def recover_stale_broadcasts_on_startup(
    *,
    session_factory: async_sessionmaker[AsyncSession] = async_session,
    has_table_check: Any | None = None,
) -> None:
    async with session_factory() as session:
        connection = await session.connection()
        has_table = await connection.run_sync(
            lambda sync_conn: (
                has_table_check(sync_conn, "Broadcasts")
                if has_table_check is not None
                else inspect(sync_conn).has_table("Broadcasts")
            )
        )
        if not has_table:
            return

        repo = BroadcastRepository(session)
        active_broadcasts = await repo.get_active()
        for broadcast in active_broadcasts:
            await repo.mark_failed(
                broadcast,
                success_count=broadcast.success_count,
                failed_count=broadcast.failed_count,
                error_message=(
                    "Рассылка остановлена из-за перезапуска процесса "
                    "и помечена как незавершённая"
                ),
            )
        await session.commit()


async def _persist_progress(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    broadcast_id: int,
    success_count: int,
    failed_count: int,
) -> None:
    async with session_factory() as session:
        repo = BroadcastRepository(session)
        broadcast = await repo.get_by_id(broadcast_id)
        if broadcast is None:
            return
        await repo.update_counts(
            broadcast,
            success_count=success_count,
            failed_count=failed_count,
        )
        await session.commit()


async def run_broadcast(
    *,
    broadcast_id: int,
    session_factory: async_sessionmaker[AsyncSession] = async_session,
    sender: Any | None = None,
) -> None:
    if sender is None:
        from app.modules.broadcasts.sender import AiogramBroadcastSender

        sender = AiogramBroadcastSender()

    async with session_factory() as session:
        repo = BroadcastRepository(session)
        broadcast = await repo.get_by_id(broadcast_id)
        if broadcast is None:
            return

        audience = TelegramUserAudienceProvider(session)
        recipients = await audience.list_recipients()
        await repo.mark_running(broadcast, total_count=len(recipients))
        await session.commit()

    success_count = 0
    failed_count = 0

    async def on_progress(next_success: int, next_failed: int) -> None:
        await _persist_progress(
            session_factory,
            broadcast_id=broadcast_id,
            success_count=next_success,
            failed_count=next_failed,
        )

    try:
        success_count, failed_count = await deliver_recipients(
            recipients=recipients,
            sender=sender,
            text=broadcast.text,
            text_format=broadcast.format,
            button_text=broadcast.button_text,
            button_url=broadcast.button_url,
            allow_paid_broadcast=broadcast.speed_mode_effective == "paid",
            target_rps=broadcast.target_rps,
            worker_count=broadcast.worker_count,
            progress_callback=on_progress,
        )
    except BroadcastDeliveryError as exc:
        success_count = exc.success_count
        failed_count = exc.failed_count
        async with session_factory() as session:
            repo = BroadcastRepository(session)
            current = await repo.get_by_id(broadcast_id)
            if current is not None:
                await repo.mark_failed(
                    current,
                    success_count=success_count,
                    failed_count=failed_count,
                    error_message=str(exc),
                )
                await session.commit()
        return
    except Exception as exc:
        async with session_factory() as session:
            repo = BroadcastRepository(session)
            current = await repo.get_by_id(broadcast_id)
            if current is not None:
                await repo.mark_failed(
                    current,
                    success_count=success_count,
                    failed_count=failed_count,
                    error_message=str(exc),
                )
                await session.commit()
        return

    async with session_factory() as session:
        repo = BroadcastRepository(session)
        current = await repo.get_by_id(broadcast_id)
        if current is None:
            return
        await repo.mark_completed(
            current,
            success_count=success_count,
            failed_count=failed_count,
        )
        await session.commit()


async def deliver_recipients(
    *,
    recipients: list[BroadcastRecipient],
    sender: Any,
    text: str,
    text_format: str,
    button_text: str | None,
    button_url: str | None,
    allow_paid_broadcast: bool,
    target_rps: int,
    worker_count: int,
    progress_callback: Any | None = None,
) -> tuple[int, int]:
    limiter = BroadcastRateLimiter(target_rps=target_rps)
    message_text = normalize_text(text, text_format)
    success_count = 0
    failed_count = 0
    processed_count = 0
    processed_lock = asyncio.Lock()
    recipient_queue: asyncio.Queue[BroadcastRecipient | None] = asyncio.Queue()
    worker_total = max(worker_count, 1)
    fatal_error: BroadcastDeliveryError | None = None

    async def maybe_emit_progress(force: bool = False) -> None:
        if progress_callback is None:
            return
        if not force and processed_count % DEFAULT_PROGRESS_BATCH_SIZE != 0:
            return
        await progress_callback(success_count, failed_count)

    async def mark_success() -> None:
        nonlocal success_count, processed_count
        async with processed_lock:
            success_count += 1
            processed_count += 1
            await maybe_emit_progress()

    async def mark_failure() -> None:
        nonlocal failed_count, processed_count
        async with processed_lock:
            failed_count += 1
            processed_count += 1
            await maybe_emit_progress()

    async def register_fatal_error(exc: Exception) -> None:
        nonlocal fatal_error
        async with processed_lock:
            if fatal_error is None:
                fatal_error = BroadcastDeliveryError(
                    str(exc),
                    success_count=success_count,
                    failed_count=failed_count,
                )

    async def send_to_recipient(recipient: BroadcastRecipient) -> None:
        while True:
            await limiter.acquire()
            try:
                await sender.send_message(
                    chat_id=recipient.chat_id,
                    text=message_text,
                    button_text=button_text,
                    button_url=button_url,
                    allow_paid_broadcast=allow_paid_broadcast,
                )
                await mark_success()
                return
            except TelegramRetryAfter as exc:
                await limiter.pause(float(exc.retry_after))
                await asyncio.sleep(float(exc.retry_after))
            except TelegramForbiddenError:
                await mark_failure()
                return
            except TelegramBadRequest as exc:
                if allow_paid_broadcast and "paid broadcast" in str(exc).lower():
                    raise
                await mark_failure()
                return
            except TelegramAPIError:
                await mark_failure()
                return
            except Exception as exc:
                await mark_failure()
                await register_fatal_error(exc)
                return

    async def worker() -> None:
        while True:
            recipient = await recipient_queue.get()
            try:
                if recipient is None:
                    return
                if fatal_error is not None:
                    continue
                await send_to_recipient(recipient)
            finally:
                recipient_queue.task_done()

    workers = [
        asyncio.create_task(worker(), name=f"broadcast-worker-{index}")
        for index in range(worker_total)
    ]

    try:
        for recipient in recipients:
            await recipient_queue.put(recipient)

        for _ in range(worker_total):
            await recipient_queue.put(None)

        await recipient_queue.join()
    finally:
        for worker_task in workers:
            if not worker_task.done():
                worker_task.cancel()
        for worker_task in workers:
            with suppress(asyncio.CancelledError):
                await worker_task

    if fatal_error is not None:
        raise fatal_error

    await maybe_emit_progress(force=True)
    return success_count, failed_count
