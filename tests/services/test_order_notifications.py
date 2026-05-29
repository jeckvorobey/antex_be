# ruff: noqa: RUF001
from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.services import order_notifications
from app.services.order_notifications import (
    _build_manager_order_text,
    notify_order_created,
    notify_order_status_changed,
    send_or_replace_user_status_message,
)


class _FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.edited: list[dict[str, object]] = []
        self.sent: list[dict[str, object]] = []
        self.edit_error: Exception | None = None

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))

    async def edit_message_text(self, text: str, chat_id: int, message_id: int, reply_markup=None):
        if self.edit_error is not None:
            raise self.edit_error
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return SimpleNamespace(message_id=88)


@pytest.mark.asyncio
async def test_user_status_message_edits_previous_message() -> None:
    bot = _FakeBot()
    order = SimpleNamespace(userNotificationMessageId=77)

    new_message_id = await send_or_replace_user_status_message(
        bot=bot,
        chat_id=700002,
        order=order,
        text="updated",
        reply_markup=None,
    )

    assert bot.edited == [
        {
            "chat_id": 700002,
            "message_id": 77,
            "text": "updated",
            "reply_markup": None,
        }
    ]
    assert bot.sent == []
    assert new_message_id == 77
    assert order.userNotificationMessageId == 77


@pytest.mark.asyncio
async def test_user_status_message_falls_back_to_send_when_edit_fails() -> None:
    bot = _FakeBot()
    bot.edit_error = TelegramBadRequest(method="editMessageText", message="message is not modified")
    order = SimpleNamespace(userNotificationMessageId=77)

    new_message_id = await send_or_replace_user_status_message(
        bot=bot,
        chat_id=700002,
        order=order,
        text="updated",
        reply_markup=None,
    )

    assert bot.edited == []
    assert bot.sent == [{"chat_id": 700002, "text": "updated", "reply_markup": None}]
    assert new_message_id == 88
    assert order.userNotificationMessageId == 88


@pytest.mark.asyncio
async def test_notify_order_created_sends_user_message_with_order_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        amountSell=100,
        currencySell="USDT",
        amountBuy=3096,
        currencyBuy="THB",
        methodGet="qrcode",
        rate=30.96,
        status=1,
        contactTelegram="sergeywebdev",
        city=None,
        userNotificationMessageId=None,
        country=SimpleNamespace(value="thailand"),
    )
    user = SimpleNamespace(
        telegram_id=700002,
        username="customer",
        phone=None,
    )
    manager = SimpleNamespace(
        telegram_id=700001,
    )

    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)
    monkeypatch.setattr(
        order_notifications,
        "get_translator",
        lambda _: (lambda key, **kwargs: key),
    )
    monkeypatch.setattr(
        order_notifications,
        "manager_order_open_chat",
        lambda *args, **kwargs: None,
    )

    await notify_order_created(order, user, manager)

    assert len(bot.sent) == 2
    assert bot.sent[0]["chat_id"] == 700002
    assert "Мы получили ваш запрос" in bot.sent[0]["text"]
    assert "💱 Направление: USDT → THB" in bot.sent[1]["text"]
    assert "💸 Сумма к обмену: 100 USDT" in bot.sent[1]["text"]


@pytest.mark.asyncio
async def test_notify_order_status_changed_adds_write_manager_button_for_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        status=2,
        user=SimpleNamespace(
            telegram_id=700002,
            username="customer",
            phone=None,
        ),
        userNotificationMessageId=55,
    )

    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)
    monkeypatch.setattr(
        order_notifications,
        "user_order_write_manager",
        lambda _, chat_url: SimpleNamespace(
            inline_keyboard=[[SimpleNamespace(text="Написать менеджеру", url=chat_url)]]
        ),
    )

    await notify_order_status_changed(order, manager_chat_url="https://t.me/manager")

    assert bot.edited[0]["chat_id"] == 700002
    assert "принята в работу" in bot.edited[0]["text"]
    assert bot.edited[0]["reply_markup"].inline_keyboard[0][0].text == "Написать менеджеру"
    assert bot.edited[0]["reply_markup"].inline_keyboard[0][0].url == "https://t.me/manager"


def test_build_manager_order_text_uses_new_created_format() -> None:
    order = SimpleNamespace(
        publicNumber="2026050019",
        amountSell=1000,
        currencySell="USDT",
        amountBuy=31000,
        currencyBuy="THB",
        methodGet="cash",
        rate=31.0,
        status=1,
        city=SimpleNamespace(name="Паттайя"),
        country=SimpleNamespace(value="Таиланд"),
    )
    user = SimpleNamespace(username="sergeywebdev")

    text = _build_manager_order_text(order, user)

    assert "🆕 Новая заявка #2026050019" in text
    assert "💱 Направление: USDT → THB" in text
    assert "💸 Сумма к обмену: 1 000 USDT" in text
    assert "💰 К выдаче: 31 000 THB" in text
    assert "📍 Паттайя, Таиланд" in text
    assert "💵 Получение: Наличные" in text
