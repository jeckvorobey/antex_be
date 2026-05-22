from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import order_notifications
from app.services.order_notifications import (
    notify_order_created,
    notify_order_status_changed,
    send_or_replace_user_status_message,
)


class _FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[dict[str, object]] = []

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return SimpleNamespace(message_id=88)


@pytest.mark.asyncio
async def test_user_status_message_replaces_previous_message() -> None:
    bot = _FakeBot()
    order = SimpleNamespace(userNotificationMessageId=77)

    new_message_id = await send_or_replace_user_status_message(
        bot=bot,
        chat_id=700002,
        order=order,
        text="updated",
        reply_markup=None,
    )

    assert bot.deleted == [(700002, 77)]
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
        "get_user_translator",
        lambda _: (lambda key, **kwargs: str(kwargs["id"])),
    )
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
    assert bot.sent[0]["text"] == "2026050008"


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
        userNotificationMessageId=None,
    )

    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)
    monkeypatch.setattr(
        order_notifications,
        "get_user_translator",
        lambda _: (lambda key, **kwargs: str(kwargs["id"])),
    )
    monkeypatch.setattr(
        order_notifications,
        "user_order_write_manager",
        lambda _, chat_url: SimpleNamespace(
            inline_keyboard=[[SimpleNamespace(text="Написать менеджеру", url=chat_url)]]
        ),
    )

    await notify_order_status_changed(order, manager_chat_url="https://t.me/manager")

    assert bot.sent[0]["chat_id"] == 700002
    assert bot.sent[0]["reply_markup"].inline_keyboard[0][0].text == "Написать менеджеру"
    assert bot.sent[0]["reply_markup"].inline_keyboard[0][0].url == "https://t.me/manager"
