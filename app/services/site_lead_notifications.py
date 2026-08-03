"""Telegram notifications for site leads."""
# ruff: noqa: RUF001

from __future__ import annotations

import logging

from app.models.site_lead import SiteLead
from app.telegram.presentation.components import build_message, truncate_text
from app.telegram.presentation.delivery import DeliveryKind, deliver
from app.telegram.presentation.models import TelegramMessageSpec

logger = logging.getLogger(__name__)


async def notify_site_lead_created(lead: SiteLead, manager) -> None:
    bot = _get_telegram_bot()
    if bot is None:
        logger.warning("Site lead notification skipped: bot is not initialized lead_id=%s", lead.id)
        return

    if manager is None or not getattr(manager, "telegram_id", None):
        logger.warning(
            "Site lead notification skipped: manager chat is unavailable lead_id=%s "
            "manager_user_id=%s",
            lead.id,
            getattr(manager, "id", None),
        )
        return

    logger.info(
        "Sending site lead notification: lead_id=%s manager_user_id=%s manager_telegram_id=%s",
        lead.id,
        getattr(manager, "id", None),
        getattr(manager, "telegram_id", None),
    )
    spec = build_site_lead_manager_message(lead)
    outcome = await deliver(
        bot,
        chat_id=manager.telegram_id,
        spec=spec,
        kind=DeliveryKind.SEND,
        reply_markup=None,
    )
    if not outcome.delivered:
        raise outcome.error or RuntimeError("Site lead notification was not delivered")
    logger.info(
        "Site lead notification sent: lead_id=%s manager_user_id=%s manager_telegram_id=%s",
        lead.id,
        getattr(manager, "id", None),
        getattr(manager, "telegram_id", None),
    )


def build_site_lead_manager_text(lead: SiteLead) -> str:
    """Возвращает regular HTML fallback для старых внутренних вызовов."""
    return build_site_lead_manager_message(lead).fallback_html


def build_site_lead_manager_message(lead: SiteLead) -> TelegramMessageSpec:
    """Собирает manager-card и сокращает только длинный свободный комментарий лида."""
    return build_message(
        family="manager",
        eyebrow="Заявка с сайта",
        title=f"Новый лид #{lead.id}",
        lead="Свяжитесь с клиентом по указанному контакту.",
        facts=(
            ("Мессенджер", _format_value(lead.messenger)),
            ("Контакт", lead.contact),
            ("Тема", _format_value(lead.topic)),
            ("Сообщение", truncate_text(lead.message or "—", limit=1_000)),
            ("Источник", lead.source),
        ),
    )


def _format_value(value: str | None) -> str:
    return value or "—"


def _get_telegram_bot():
    from app.telegram import bot as telegram_bot

    return telegram_bot.bot
