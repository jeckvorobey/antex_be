"""Telegram-уведомления по операциям ATXG (credit/debit)."""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)


async def notify_aex_operation(
    db: AsyncSession,
    *,
    user_id: int,
    operation_type: str,
    amount: Decimal,
    description: str | None = None,
) -> None:
    """Best-effort Telegram-уведомление пользователю после credit/debit ATXG.

    Args:
        db: AsyncSession (для загрузки пользователя)
        user_id: ID пользователя
        operation_type: 'credit' или 'debit'
        amount: сумма операции
        description: описание операции
    """
    user = await UserRepository(db).get_one(user_id)
    if user is None or not user.telegram_id:
        logger.debug(
            "ATXG notification skipped: user %s not found or has no telegram_id",
            user_id,
        )
        return

    from app.telegram import bot as telegram_bot

    if telegram_bot.bot is None:
        logger.warning("ATXG notification skipped: bot is not initialized")
        return

    text = _build_aex_notification_text(
        operation_type=operation_type,
        amount=amount,
        description=description,
    )

    try:
        await telegram_bot.bot.send_message(
            chat_id=user.telegram_id,
            text=text,
        )
    except Exception:
        logger.exception(
            "Failed to send ATXG notification: user_id=%s operation=%s",
            user_id,
            operation_type,
        )


def _build_aex_notification_text(
    *,
    operation_type: str,
    amount: Decimal,
    description: str | None = None,
) -> str:
    """Построить текст уведомления для Telegram."""
    if operation_type == "credit":
        emoji = "💰"
        label = "Начисление ATXG"
    else:
        emoji = "💸"
        label = "Списание ATXG"

    lines = [
        f"{emoji} {label}",
        "",
        f"Сумма: {amount} ATXG",
    ]

    if description:
        lines.append(f"Описание: {description}")

    return "\n".join(lines)
