from __future__ import annotations

import os
from types import SimpleNamespace

from aiogram.types import User as TgUser

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.telegram.handlers import start as start_handler
from app.telegram.i18n import get_translator
from app.telegram.keyboards import (
    choose_buy_currency,
    choose_currency,
    confirm_exchange,
    home,
    manager_home,
    manager_order_close,
    manager_order_open_chat,
    obtaining,
    review_link,
)


class _FakeDbSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        return None


class _FakeConfigRepo:
    def __init__(self, db) -> None:
        self.db = db

    async def get_or_create(self):
        return SimpleNamespace(enabled=True)


class _FakeMessage:
    def __init__(self, user: TgUser) -> None:
        self.from_user = user
        self.answers: list[dict[str, object]] = []
        self.edits: list[dict[str, object]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append({"text": text, "reply_markup": reply_markup})

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edits.append({"text": text, "reply_markup": reply_markup})


class _FakeCallback:
    def __init__(self, data: str, user: TgUser) -> None:
        self.data = data
        self.from_user = user
        self.message = _FakeMessage(user)
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append({"text": text, "show_alert": show_alert})


async def test_home_keyboard_without_webapp_url(monkeypatch) -> None:
    monkeypatch.setattr("app.telegram.keyboards.settings.frontend_webapp_url", None)

    kb = home(get_translator("ru"))

    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 2
    assert kb.inline_keyboard[0][0].callback_data == "menu:exchange"
    assert kb.inline_keyboard[0][1].callback_data == "menu:orders"


async def test_home_keyboard_with_webapp_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.telegram.keyboards.settings.frontend_webapp_url",
        "https://example.com/miniapp",
    )

    kb = home(get_translator("ru"))

    assert len(kb.inline_keyboard) == 2
    assert len(kb.inline_keyboard[1]) == 1
    assert kb.inline_keyboard[1][0].web_app is not None
    assert kb.inline_keyboard[1][0].web_app.url == "https://example.com/miniapp"


async def test_manager_home_keyboard_has_new_requests_and_site(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.telegram.keyboards.settings.frontend_webapp_url",
        "https://example.com/miniapp",
    )

    kb = manager_home(get_translator("ru"))

    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].text == "🆕 Новые заявки"
    assert kb.inline_keyboard[0][0].callback_data == "manager:site_leads"
    assert kb.inline_keyboard[1][0].text == "🚀 Открыть сайт"
    assert kb.inline_keyboard[1][0].web_app is not None
    assert kb.inline_keyboard[1][0].web_app.url == "https://example.com/miniapp"


async def test_start_always_uses_home_keyboard(monkeypatch) -> None:
    user = TgUser(
        id=777,
        is_bot=False,
        first_name="Tester",
        last_name="User",
        username="tester",
        language_code="ru",
        is_premium=False,
    )
    message = _FakeMessage(user)

    fake_db = _FakeDbSession()

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return (SimpleNamespace(role=3), False)

    monkeypatch.setattr(start_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(start_handler, "ConfigRepository", _FakeConfigRepo)
    monkeypatch.setattr(start_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(
        "app.telegram.keyboards.settings.frontend_webapp_url", "https://example.com/app"
    )

    await start_handler.cmd_start(message)

    assert len(message.answers) == 1
    reply_markup = message.answers[0]["reply_markup"]
    assert reply_markup is not None
    assert len(reply_markup.inline_keyboard) == 2
    assert reply_markup.inline_keyboard[0][0].callback_data == "menu:exchange"
    assert reply_markup.inline_keyboard[0][1].callback_data == "menu:orders"
    assert reply_markup.inline_keyboard[1][0].web_app is not None
    assert reply_markup.inline_keyboard[1][0].web_app.url == "https://example.com/app"


async def test_start_uses_manager_keyboard_for_manager(monkeypatch) -> None:
    user = TgUser(
        id=777,
        is_bot=False,
        first_name="Manager",
        last_name="User",
        username="manager",
        language_code="ru",
        is_premium=False,
    )
    message = _FakeMessage(user)
    fake_db = _FakeDbSession()

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return (SimpleNamespace(role=2), False)

    monkeypatch.setattr(start_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(start_handler, "ConfigRepository", _FakeConfigRepo)
    monkeypatch.setattr(start_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(
        "app.telegram.keyboards.settings.frontend_webapp_url", "https://example.com/app"
    )

    await start_handler.cmd_start(message)

    assert len(message.answers) == 1
    reply_markup = message.answers[0]["reply_markup"]
    assert reply_markup.inline_keyboard[0][0].callback_data == "manager:site_leads"
    assert reply_markup.inline_keyboard[1][0].web_app.url == "https://example.com/app"


async def test_manager_site_leads_callback_lists_recent_leads(monkeypatch) -> None:
    user = TgUser(
        id=777,
        is_bot=False,
        first_name="Manager",
        username="manager",
        language_code="ru",
    )
    callback = _FakeCallback("manager:site_leads", user)
    fake_db = _FakeDbSession()
    leads = [
        SimpleNamespace(id=2, messenger="Max", contact="79206629860"),
        SimpleNamespace(id=1, messenger="Telegram", contact="@client"),
    ]

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return (SimpleNamespace(role=2), False)

    class _FakeSiteLeadRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def list_recent(self, *, limit: int = 10):
            assert limit == 10
            return leads

    monkeypatch.setattr(start_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(start_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(start_handler, "SiteLeadRepository", _FakeSiteLeadRepo)

    await start_handler.manager_site_leads(callback)

    assert callback.message.edits[0]["text"] == get_translator("ru")("manager-site-leads-header")
    reply_markup = callback.message.edits[0]["reply_markup"]
    assert reply_markup.inline_keyboard[0][0].text == "🆕 #2 Max: 79206629860"
    assert reply_markup.inline_keyboard[0][0].callback_data == "manager:site_lead:2"
    assert reply_markup.inline_keyboard[1][0].text == "🆕 #1 Telegram: @client"
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_exchange_keyboards_are_backend_driven() -> None:
    translator = get_translator("ru")

    sell_kb = choose_currency(translator, ["RUB", "USDT", "THB"])
    buy_kb = choose_buy_currency(translator, ["THB", "GEL"])
    methods_kb = obtaining(translator, ["cash", "card"])
    confirm_kb = confirm_exchange(translator)

    assert [button.text for button in sell_kb.inline_keyboard[0]] == [
        "🇷🇺 RUB",
        "₮ USDT",
        "🇹🇭 THB",
    ]
    assert [button.callback_data for button in buy_kb.inline_keyboard[0]] == [
        "exchange:buy:THB",
        "exchange:buy:GEL",
    ]
    assert [button.callback_data for button in methods_kb.inline_keyboard[0]] == [
        "method:cash",
        "method:card",
    ]
    assert [button.callback_data for button in confirm_kb.inline_keyboard[0]] == [
        "exchange:confirm",
        "fsm:back",
    ]
    assert confirm_kb.inline_keyboard[0][0].style == "success"
    assert confirm_kb.inline_keyboard[0][1].style == "primary"
    assert confirm_kb.inline_keyboard[1][0].style == "danger"
    assert confirm_kb.inline_keyboard[1][0].callback_data == "fsm:cancel"


async def test_manager_order_keyboards_use_new_callbacks() -> None:
    translator = get_translator("ru")

    open_chat = manager_order_open_chat(
        translator,
        order_id=17,
        chat_url="https://t.me/customer",
    )
    close_order = manager_order_close(
        translator,
        order_id=17,
        chat_url="https://t.me/customer",
    )
    review = review_link(translator, "https://example.com/review")

    assert len(open_chat.inline_keyboard) == 2
    assert open_chat.inline_keyboard[0][0].callback_data == "op:cancel:17"
    assert open_chat.inline_keyboard[0][0].style == "danger"
    assert open_chat.inline_keyboard[0][1].callback_data == "op:take:17"
    assert open_chat.inline_keyboard[0][1].style == "success"
    assert open_chat.inline_keyboard[1][0].url == "https://t.me/customer"
    assert open_chat.inline_keyboard[1][0].text == "💬 Написать в чат"

    assert close_order.inline_keyboard[0][0].callback_data == "op:cancel:17"
    assert close_order.inline_keyboard[0][0].style == "danger"
    assert close_order.inline_keyboard[0][1].callback_data == "op:close:17"
    assert close_order.inline_keyboard[0][1].style == "success"
    assert close_order.inline_keyboard[1][0].url == "https://t.me/customer"
    assert review.inline_keyboard[0][0].url == "https://example.com/review"
    assert review.inline_keyboard[0][0].style == "success"
