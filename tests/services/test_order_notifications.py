# ruff: noqa: RUF001
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.services import order_notifications
from app.services.order_notifications import (
    _build_manager_order_text,
    build_manager_status_text,
    notify_order_created,
    notify_order_status_changed,
    send_or_replace_user_status_message,
)
from app.telegram.i18n import get_translator


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

    await notify_order_created(order, user, manager)

    assert len(bot.sent) == 2
    assert bot.sent[0]["chat_id"] == 700002
    assert "Мы получили ваш запрос" in bot.sent[0]["text"]
    assert bot.sent[0]["reply_markup"].inline_keyboard[0][0].callback_data == "menu:orders"
    assert bot.sent[0]["reply_markup"].inline_keyboard[1][0].callback_data == "fsm:cancel"
    manager_markup = cast(Any, bot.sent[1]["reply_markup"])
    assert len(manager_markup.inline_keyboard) == 1
    assert manager_markup.inline_keyboard[0][0].callback_data == "op:cancel:8"
    assert manager_markup.inline_keyboard[0][1].callback_data == "op:take:8"
    text = str(bot.sent[1]["text"])
    assert "🌍 Страна: Таиланд" in text
    assert "📈 Курс: 30.96" in text
    assert "💸 Отдаёте: 100 ₮ USDT" in text
    assert "💰 Получаете: 3,096 🇹🇭 THB" in text
    assert "🧾 Способ получения: Наличные по QR" in text
    assert "👤 Пользователь: @customer" in text


def test_build_manager_status_text_uses_new_middle_format_for_processing() -> None:
    order = SimpleNamespace(
        publicNumber="2026050020",
        amountSell=2350,
        currencySell="USDT",
        amountBuy=77250,
        currencyBuy="THB",
        methodGet="qrcode",
        rate=32.8723,
        status=2,
        city=SimpleNamespace(name="Бангкок"),
        country=SimpleNamespace(value="thailand"),
        user=SimpleNamespace(username="sergeywebdev"),
    )

    text = build_manager_status_text(order)

    assert "🟢 Заявка #2026050020" in text
    assert "⏳ Статус: В работе" in text
    assert "🌍 Страна: Таиланд" in text
    assert "🏙️ Город: Бангкок" in text
    assert "📈 Курс: 32.8723" in text
    assert "💸 Отдаёте: 2,350 ₮ USDT" in text
    assert "💰 Получаете: 77,250 🇹🇭 THB" in text
    assert "🧾 Способ получения: Наличные по QR" in text
    assert "👤 Пользователь: @sergeywebdev" in text
    assert "💬 Ожидает завершения обмена" in text


def test_build_manager_status_text_uses_shared_middle_format_for_completed() -> None:
    order = SimpleNamespace(
        publicNumber="2026050026",
        amountSell=10000,
        currencySell="USDT",
        amountBuy=27100,
        currencyBuy="GEL",
        methodGet="cash",
        rate=2.71,
        status=3,
        city=SimpleNamespace(name="Батуми"),
        country=SimpleNamespace(value="georgia"),
        user=SimpleNamespace(username="sergeywebdev"),
    )

    text = build_manager_status_text(order)

    assert "✅ Заявка #2026050026 завершена" in text
    assert "🌍 Страна: Грузия" in text
    assert "🏙️ Город: Батуми" in text
    assert "📈 Курс: 2.71" in text
    assert "💸 Отдаёте: 10,000 ₮ USDT" in text
    assert "💰 Получаете: 27,100 🇬🇪 GEL" in text
    assert "🧾 Способ получения: Доставка наличных" in text
    assert "🏁 Обмен успешно выполнен" in text
    assert "💱 Направление:" not in text
    assert "👤 Пользователь:" not in text


@pytest.mark.asyncio
async def test_notify_order_status_changed_adds_summary_for_completed_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    order = SimpleNamespace(
        id=9,
        publicNumber="2026050009",
        status=3,
        country=SimpleNamespace(value="thailand"),
        city=SimpleNamespace(name="Бангкок"),
        rate=31.5,
        amountSell=1500,
        currencySell="USDT",
        amountBuy=47250,
        currencyBuy="THB",
        methodGet="cash",
        user=SimpleNamespace(
            telegram_id=700002,
            username="customer",
            phone=None,
        ),
        userNotificationMessageId=55,
    )

    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    await notify_order_status_changed(order, manager_chat_url="https://t.me/manager")

    assert bot.edited[0]["chat_id"] == 700002
    text = str(bot.edited[0]["text"])
    assert "🎉 Заявка" in text and "успешно завершена." in text
    assert "🌍 Страна: Таиланд" in text
    assert "🏙️ Город: Бангкок" in text
    assert "📈 Курс: 31.5" in text
    assert "💸 Отдаёте: 1,500 ₮ USDT" in text
    assert "💰 Получаете: 47,250 🇹🇭 THB" in text
    assert "🧾 Способ получения: Доставка наличных" in text
    assert (
        "Спасибо, что воспользовались нашим сервисом!\n\n"
        "Мы ценим обратную связь. За видео-отзыв (кружок) предоставляем "
        "<b>бонус 5$ к следующему обмену 💰</b>\n\n"
        "⭐ Будем рады вашему отзыву. Это помогает нам становиться лучше."
    ) in text
    reply_markup = cast(Any, bot.edited[0]["reply_markup"])
    assert reply_markup.inline_keyboard[0][0].text == "⭐ Оставить отзыв"
    assert reply_markup.inline_keyboard[1][0].text == "🏠 Главное меню"
    assert reply_markup.inline_keyboard[1][0].callback_data == "fsm:cancel"


@pytest.mark.asyncio
async def test_notify_order_status_changed_adds_write_manager_button_for_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        status=2,
        amountSell=5000,
        currencySell="RUB",
        user=SimpleNamespace(
            telegram_id=700002,
            username="customer",
            phone=None,
        ),
        userNotificationMessageId=55,
    )

    user_button: dict[str, object] = {}

    def _fake_user_order_write_manager(*args, **kwargs):
        user_button.update(kwargs)
        return SimpleNamespace(
            inline_keyboard=[
                [SimpleNamespace(text="💬 Написать в чат", url="https://t.me/share/url")]
            ]
        )

    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)
    monkeypatch.setattr(
        order_notifications,
        "user_order_write_manager",
        _fake_user_order_write_manager,
    )

    await notify_order_status_changed(order, manager_chat_url="https://t.me/manager")

    assert bot.edited[0]["chat_id"] == 700002
    assert "принята в работу" in bot.edited[0]["text"]
    reply_markup = cast(Any, bot.edited[0]["reply_markup"])
    user_text = str(user_button["message_text"]).replace("\u2068", "").replace("\u2069", "")
    assert user_text == (
        "Здравствуйте! По заявке #2026050008 на сумму 5,000 RUB подтверждаю готовность к обмену."
    )
    assert reply_markup.inline_keyboard[0][0].text == "💬 Написать в чат"
    assert reply_markup.inline_keyboard[0][0].url == "https://t.me/share/url"


def test_notify_order_created_manager_keyboard_has_no_chat_button() -> None:
    markup = order_notifications.manager_order_open_chat(
        get_translator("ru"),
        order_id=8,
    )

    assert len(markup.inline_keyboard) == 1
    assert markup.inline_keyboard[0][0].callback_data == "op:cancel:8"
    assert markup.inline_keyboard[0][1].callback_data == "op:take:8"


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
    assert "🌍 Страна: Таиланд" in text
    assert "🏙️ Город: Паттайя" in text
    assert "📈 Курс: 31.0" in text
    assert "💸 Отдаёте: 1,000 ₮ USDT" in text
    assert "💰 Получаете: 31,000 🇹🇭 THB" in text
    assert "🧾 Способ получения: Доставка наличных" in text
    assert "👤 Пользователь: @sergeywebdev" in text
    assert "⏳ Ожидает обработки менеджером" in text
