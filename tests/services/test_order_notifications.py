# ruff: noqa: RUF001
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNotFound

from app.services import order_notifications
from app.services.order_notifications import (
    DeliveryOutcome,
    _build_manager_order_text,
    build_chat_url_for_user,
    build_manager_contact_url,
    build_manager_status_text,
    edit_manager_order_card,
    notify_order_created,
    notify_order_status_changed,
    send_customer_handoff,
    send_or_replace_user_status_message,
)
from app.telegram.i18n import get_translator


class _FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.edited: list[dict[str, object]] = []
        self.sent: list[dict[str, object]] = []
        self.rich_sent: list[dict[str, object]] = []
        self.edit_error: Exception | None = None
        self.rich_edit_error: Exception | None = None
        self.rich_error: Exception | None = None

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))

    async def edit_message_text(
        self,
        text: str | None = None,
        chat_id: int | None = None,
        message_id: int | None = None,
        reply_markup=None,
        rich_message=None,
    ):
        error = self.rich_edit_error if rich_message is not None else self.edit_error
        if error is not None:
            raise error
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "rich_message": rich_message,
                "reply_markup": reply_markup,
            }
        )

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return SimpleNamespace(message_id=88)

    async def send_rich_message(self, chat_id: int, rich_message, reply_markup=None):
        if self.rich_error is not None:
            raise self.rich_error
        self.rich_sent.append(
            {"chat_id": chat_id, "rich_message": rich_message, "reply_markup": reply_markup}
        )
        return SimpleNamespace(message_id=89)


class _FakeEditableMessage:
    def __init__(self) -> None:
        self.edits: list[dict[str, object]] = []
        self.rich_error: Exception | None = None

    async def edit_text(self, text=None, rich_message=None, reply_markup=None):
        if rich_message is not None and self.rich_error is not None:
            raise self.rich_error
        self.edits.append(
            {"text": text, "rich_message": rich_message, "reply_markup": reply_markup}
        )


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
            "rich_message": None,
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

    assert len(bot.sent) == 1
    assert len(bot.rich_sent) == 1
    assert bot.sent[0]["chat_id"] == 700002
    assert "Заявка №" in bot.sent[0]["text"]
    assert bot.sent[0]["reply_markup"].inline_keyboard[0][0].callback_data == "menu:orders"
    assert bot.sent[0]["reply_markup"].inline_keyboard[1][0].callback_data == "fsm:cancel"
    manager_markup = cast(Any, bot.rich_sent[0]["reply_markup"])
    assert len(manager_markup.inline_keyboard) == 1
    assert manager_markup.inline_keyboard[0][0].callback_data == "op:cancel:8"
    assert manager_markup.inline_keyboard[0][1].callback_data == "op:take:8"
    text = str(bot.rich_sent[0]["rich_message"].html)
    assert "<footer>Статус заявки</footer>" in text
    assert "Страна</td><td><b>Таиланд" in text
    assert "Курс</td><td><b>30.96" in text
    assert "Отдаёте</td><td><b>100 ₮ USDT" in text
    assert "Получаете</td><td><b>3 096 🇹🇭 THB" in text
    assert "Способ получения</td><td><b>Наличные по QR" in text
    assert "Пользователь</td><td><b>@customer" in text


@pytest.mark.asyncio
async def test_manager_order_card_edit_falls_back_once_to_regular_html() -> None:
    message = _FakeEditableMessage()
    message.rich_error = TelegramBadRequest(
        method="editMessageText",
        message="rich message is unsupported",
    )
    order = SimpleNamespace(
        publicNumber="2026050008",
        status=2,
        amountSell=10000,
        currencySell="USDT",
        amountBuy=325000,
        currencyBuy="THB",
        user=SimpleNamespace(username="customer"),
    )

    delivery = await edit_manager_order_card(
        message=message,
        order=order,
        reply_markup=SimpleNamespace(),
    )

    assert delivery == DeliveryOutcome.FALLBACK
    assert len(message.edits) == 1
    assert message.edits[0]["rich_message"] is None
    assert "Заявка #2026050008 принята в работу" in message.edits[0]["text"]


@pytest.mark.asyncio
async def test_customer_handoff_uses_rich_message_and_public_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        amountSell=10000,
        currencySell="USDT",
        amountBuy=325000,
        currencyBuy="THB",
        rate=32.5,
        methodGet="qrcode",
        country=SimpleNamespace(value="thailand"),
        city=SimpleNamespace(name="Бангкок"),
        user=SimpleNamespace(telegram_id=700002, language_code="ru"),
    )
    manager = SimpleNamespace(username="manager")
    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    delivery = await send_customer_handoff(order, manager)

    assert delivery == DeliveryOutcome.RICH
    assert bot.sent == []
    assert bot.rich_sent[0]["rich_message"].html is not None
    assert "Заявка #2026050008" in bot.rich_sent[0]["rich_message"].html
    assert "10 000 ₮ USDT" in bot.rich_sent[0]["rich_message"].html
    button = bot.rich_sent[0]["reply_markup"].inline_keyboard[0][0]
    assert button.text == "💬 Написать менеджеру"
    assert "text=" in button.url
    assert "%232026050008" in button.url


@pytest.mark.asyncio
async def test_customer_handoff_falls_back_once_to_regular_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    bot.rich_error = TelegramBadRequest(method="sendRichMessage", message="method not found")
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        user=SimpleNamespace(telegram_id=700002, language_code="ru"),
    )
    manager = SimpleNamespace(username="manager")
    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    delivery = await send_customer_handoff(order, manager)

    assert delivery == DeliveryOutcome.FALLBACK
    assert bot.rich_sent == []
    assert len(bot.sent) == 1
    assert "Напишите менеджеру первым" in bot.sent[0]["text"]
    assert "поле ввода" not in bot.sent[0]["text"]


@pytest.mark.asyncio
async def test_customer_handoff_falls_back_when_rich_method_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    bot.rich_error = TelegramNotFound(method="sendRichMessage", message="method not found")
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        user=SimpleNamespace(telegram_id=700002, language_code="ru"),
    )
    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    delivery = await send_customer_handoff(order, SimpleNamespace(username="manager"))

    assert delivery == DeliveryOutcome.FALLBACK
    assert bot.rich_sent == []
    assert len(bot.sent) == 1


@pytest.mark.asyncio
async def test_customer_handoff_returns_failed_without_duplicate_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    bot.rich_error = TelegramForbiddenError(method="sendRichMessage", message="bot blocked")
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        user=SimpleNamespace(telegram_id=700002, language_code="ru"),
    )
    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    delivery = await send_customer_handoff(order, SimpleNamespace(username="manager"))

    assert delivery == DeliveryOutcome.FAILED
    assert bot.sent == []
    assert bot.rich_sent == []


@pytest.mark.asyncio
async def test_customer_handoff_edits_existing_status_with_rich_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        amountSell=10000,
        currencySell="USDT",
        amountBuy=325000,
        currencyBuy="THB",
        user=SimpleNamespace(telegram_id=700002, language_code="ru"),
        userNotificationMessageId=55,
    )
    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    delivery = await send_customer_handoff(order, SimpleNamespace(username="manager"))

    assert delivery == DeliveryOutcome.RICH
    assert bot.sent == []
    assert bot.rich_sent == []
    assert bot.edited[0]["message_id"] == 55
    assert bot.edited[0]["text"] is None
    assert bot.edited[0]["rich_message"].html is not None
    assert order.userNotificationMessageId == 55


@pytest.mark.asyncio
async def test_customer_handoff_falls_back_to_regular_edit_without_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    bot.rich_edit_error = TelegramBadRequest(
        method="editMessageText",
        message="rich message is unsupported",
    )
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        amountSell=10000,
        currencySell="USDT",
        amountBuy=325000,
        currencyBuy="THB",
        user=SimpleNamespace(telegram_id=700002, language_code="ru"),
        userNotificationMessageId=55,
    )
    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    delivery = await send_customer_handoff(order, SimpleNamespace(username="manager"))

    assert delivery == DeliveryOutcome.FALLBACK
    assert len(bot.edited) == 1
    assert "Напишите менеджеру первым" in bot.edited[0]["text"]
    assert bot.sent == []
    assert bot.rich_sent == []


def test_manager_contact_url_rejects_invalid_username() -> None:
    assert build_manager_contact_url(SimpleNamespace(username="manager?start=evil")) is None


def test_client_chat_url_rejects_invalid_username_and_uses_telegram_id() -> None:
    user = SimpleNamespace(username="customer?text=spoofed", telegram_id=700002)

    assert build_chat_url_for_user(user) == "tg://user?id=700002"


@pytest.mark.asyncio
async def test_customer_handoff_without_manager_username_fails_without_leaking_draft(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = _FakeBot()
    order = SimpleNamespace(
        id=8,
        publicNumber="2026050008",
        user=SimpleNamespace(telegram_id=700002, language_code="ru"),
    )
    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    delivery = await send_customer_handoff(order, SimpleNamespace(username=None))

    assert delivery == DeliveryOutcome.FAILED
    assert bot.sent == [] and bot.rich_sent == []
    assert "manager_username_missing" in caplog.text
    assert "Готов продолжить обмен" not in caplog.text
    assert "https://t.me/" not in caplog.text


@pytest.mark.asyncio
async def test_notify_order_created_can_skip_duplicate_customer_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = _FakeBot()
    order = SimpleNamespace(
        id=9,
        publicNumber="2026050009",
        amountSell=100,
        currencySell="USDT",
        amountBuy=3096,
        currencyBuy="THB",
        methodGet="qrcode",
        rate=30.96,
        status=1,
        contactTelegram="customer",
        city=None,
        country=SimpleNamespace(value="thailand"),
    )
    user = SimpleNamespace(telegram_id=700002, username="customer", phone=None)
    manager = SimpleNamespace(telegram_id=700001)

    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    await notify_order_created(order, user, manager, notify_user=False)

    assert bot.sent == []
    assert [message["chat_id"] for message in bot.rich_sent] == [700001]


@pytest.mark.asyncio
async def test_notify_order_created_reports_failed_manager_delivery(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = _FakeBot()
    bot.rich_error = TelegramForbiddenError(method="sendRichMessage", message="bot blocked")
    order = SimpleNamespace(
        id=9,
        publicNumber="2026050009",
        status=1,
        user=SimpleNamespace(username="customer"),
    )
    user = SimpleNamespace(telegram_id=700002, username="customer", phone=None)
    manager = SimpleNamespace(id=7, telegram_id=700001)
    monkeypatch.setattr(order_notifications, "_get_telegram_bot", lambda: bot)

    delivery = await notify_order_created(order, user, manager, notify_user=False)

    assert delivery == DeliveryOutcome.FAILED
    assert "Order notification sent to manager" not in caplog.text
    assert "Order notification delivery to manager failed" in caplog.text


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

    assert "✅ Заявка #2026050020 принята в работу" in text
    assert "Страна: <b>Таиланд</b>" in text
    assert "Город: <b>Бангкок</b>" in text
    assert "Курс: <b>32.8723</b>" in text
    assert "Отдаёте: <b>2 350 ₮ USDT</b>" in text
    assert "Получаете: <b>77 250 🇹🇭 THB</b>" in text
    assert "Способ получения: <b>Наличные по QR</b>" in text
    assert "Пользователь: <b>@sergeywebdev</b>" in text
    assert "Клиенту отправлена просьба начать диалог" in text


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
    assert "Страна: <b>Грузия</b>" in text
    assert "Город: <b>Батуми</b>" in text
    assert "Курс: <b>2.71</b>" in text
    assert "Отдаёте: <b>10 000 ₮ USDT</b>" in text
    assert "Получаете: <b>27 100 🇬🇪 GEL</b>" in text
    assert "Способ получения: <b>Доставка наличных</b>" in text
    assert "Обмен успешно выполнен" in text
    assert "💱 Направление:" not in text
    assert "Пользователь: <b>@sergeywebdev</b>" in text


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
    assert user_text == "Здравствуйте! Я по заявке #2026050008. Готов продолжить обмен."
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
    assert "Страна: <b>Таиланд</b>" in text
    assert "Город: <b>Паттайя</b>" in text
    assert "Курс: <b>31</b>" in text
    assert "Отдаёте: <b>1 000 ₮ USDT</b>" in text
    assert "Получаете: <b>31 000 🇹🇭 THB</b>" in text
    assert "Способ получения: <b>Доставка наличных</b>" in text
    assert "Пользователь: <b>@sergeywebdev</b>" in text
    assert "Ожидает решения менеджера" in text
