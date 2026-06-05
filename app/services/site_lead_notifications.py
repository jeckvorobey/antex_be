"""Telegram notifications for site leads."""
# ruff: noqa: RUF001

from __future__ import annotations

import logging

from app.models.site_lead import SiteLead

logger = logging.getLogger(__name__)


async def notify_site_lead_created(lead: SiteLead, manager) -> None:
    bot = _get_telegram_bot()
    if bot is None:
        logger.warning("Site lead notification skipped: bot is not initialized")
        return

    if manager is None or not getattr(manager, "telegram_id", None):
        logger.warning("Site lead notification skipped: manager chat is unavailable")
        return

    await bot.send_message(
        chat_id=manager.telegram_id,
        text=build_site_lead_manager_text(lead),
        reply_markup=None,
    )


def build_site_lead_manager_text(lead: SiteLead) -> str:
    return "\n".join(
        [
            f"🆕 Заявка с сайта #{lead.id}",
            "",
            f"💬 Мессенджер: {_format_value(lead.messenger)}",
            f"👤 Контакт: {lead.contact}",
            f"📌 Тема: {_format_value(lead.topic)}",
            f"📝 Сообщение: {lead.message}",
            f"🌐 Источник: {lead.source}",
        ]
    )


def _format_value(value: str | None) -> str:
    return value or "—"


def _get_telegram_bot():
    from app.telegram import bot as telegram_bot

    return telegram_bot.bot
