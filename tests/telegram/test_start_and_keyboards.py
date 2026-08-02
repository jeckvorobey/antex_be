from __future__ import annotations

import os
from datetime import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from aiogram.types import User as TgUser

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.enums.country import Country
from app.telegram.handlers import start as start_handler
from app.telegram.i18n import get_translator
from app.telegram.keyboards import (
    amount_controls,
    back_to_main_menu,
    choose_city,
    choose_country,
    choose_currency,
    choose_service,
    confirm_exchange,
    confirm_off_hours_exchange,
    manager_home,
    manager_order_close,
    manager_order_open_chat,
    obtaining,
    order_created_actions,
    orders_pagination,
    review_link,
    user_order_write_manager,
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


class _FakeState:
    def __init__(self) -> None:
        self.cleared = False
        self.state = None

    async def clear(self) -> None:
        self.cleared = True

    async def set_state(self, state) -> None:
        self.state = getattr(state, "state", state)


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


async def test_country_keyboard_has_orders_under_countries(monkeypatch) -> None:
    monkeypatch.setattr("app.telegram.keyboards.settings.frontend_webapp_url", None)

    kb = choose_country(get_translator("ru"))

    assert [button.callback_data for button in kb.inline_keyboard[0]] == [
        "exchange:country:thailand",
        "exchange:country:vietnam",
        "exchange:country:georgia",
    ]
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[1][0].text == "📋 Мои заявки"
    assert kb.inline_keyboard[1][0].callback_data == "menu:orders"


async def test_country_keyboard_keeps_open_app_button(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.telegram.keyboards.settings.frontend_webapp_url",
        "https://example.com/app",
    )

    kb = choose_country(get_translator("ru"))

    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[1][0].callback_data == "menu:orders"
    assert kb.inline_keyboard[2][0].text == "🚀 Открыть приложение"
    assert kb.inline_keyboard[2][0].web_app is not None
    assert kb.inline_keyboard[2][0].web_app.url == "https://example.com/app"


def test_orders_pagination_keyboard_appears_only_after_ten_orders() -> None:
    translate = get_translator("ru")

    short_kb = orders_pagination(translate, page=1, total=10, page_size=10)
    assert len(short_kb.inline_keyboard) == 1
    assert short_kb.inline_keyboard[0][0].callback_data == "fsm:cancel"

    paged_kb = orders_pagination(translate, page=2, total=21, page_size=10)
    assert [button.callback_data for button in paged_kb.inline_keyboard[0]] == [
        "menu:orders:page:1",
        "menu:orders:noop",
        "menu:orders:page:3",
    ]
    assert paged_kb.inline_keyboard[0][1].text == "2/3"
    assert paged_kb.inline_keyboard[1][0].callback_data == "fsm:cancel"


async def test_service_keyboard_has_short_labels_and_back_button() -> None:
    kb = choose_service(get_translator("ru"))

    assert [button.text for button in kb.inline_keyboard[0]] == [
        "🚕 Доставка наличных",
        "🏧 Наличные по QR",
    ]
    assert [button.text for button in kb.inline_keyboard[1]] == [
        "💳 Перевод",
        "🧰 Оплата сервисов",
    ]
    assert kb.inline_keyboard[2][0].text == "◀ Назад"
    assert kb.inline_keyboard[2][0].callback_data == "fsm:back"


async def test_currency_keyboard_has_usdt_icon_back_and_cancel() -> None:
    kb = choose_currency(get_translator("ru"), ["USDT", "RUB"])

    assert [button.text for button in kb.inline_keyboard[0]] == ["₮ USDT", "🇷🇺 RUB"]
    assert [button.callback_data for button in kb.inline_keyboard[1]] == [
        "fsm:back",
        "fsm:cancel",
    ]
    assert [button.text for button in kb.inline_keyboard[1]] == ["◀ Назад", "❌ Отменить"]
    assert kb.inline_keyboard[1][0].style == "primary"
    assert kb.inline_keyboard[1][1].style == "danger"


async def test_manager_home_keyboard_has_new_requests_and_site(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.telegram.keyboards.settings.frontend_webapp_url",
        "https://example.com/miniapp",
    )

    kb = manager_home(get_translator("ru"))

    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].text == "🆕 Новые заявки"
    assert kb.inline_keyboard[0][0].callback_data == "manager:new_orders"
    assert kb.inline_keyboard[1][0].text == "🚀 Открыть приложение"
    assert kb.inline_keyboard[1][0].web_app is not None
    assert kb.inline_keyboard[1][0].web_app.url == "https://example.com/miniapp"


async def test_start_shows_country_selection_for_customer(monkeypatch) -> None:
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

    await start_handler.cmd_start(message, _FakeState())

    assert len(message.answers) == 1
    reply_markup = message.answers[0]["reply_markup"]
    assert reply_markup is not None
    assert "выберите страну в списке ниже" in str(message.answers[0]["text"])
    assert [button.callback_data for button in reply_markup.inline_keyboard[0]] == [
        "exchange:country:thailand",
        "exchange:country:vietnam",
        "exchange:country:georgia",
    ]
    assert [button.callback_data for button in reply_markup.inline_keyboard[1]] == [
        "menu:orders",
    ]


async def test_start_uses_configured_manager_schedule_in_customer_welcome(monkeypatch) -> None:
    user = TgUser(
        id=778,
        is_bot=False,
        first_name="Tester",
        last_name="User",
        username="tester",
        language_code="ru",
        is_premium=False,
    )
    message = _FakeMessage(user)
    fake_db = _FakeDbSession()

    class _ConfiguredScheduleRepo(_FakeConfigRepo):
        async def get_or_create(self):
            return SimpleNamespace(
                enabled=True,
                manager_schedule_enabled=True,
                manager_working_days_utc=[1, 2, 3, 4, 5],
                manager_start_time_utc=time(7),
                manager_end_time_utc=time(19),
            )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return (SimpleNamespace(role=3), False)

    monkeypatch.setattr(start_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(start_handler, "ConfigRepository", _ConfiguredScheduleRepo)
    monkeypatch.setattr(start_handler, "check_user", _fake_check_user)

    await start_handler.cmd_start(message, _FakeState())

    welcome_text = str(message.answers[0]["text"]).replace("\u2068", "").replace("\u2069", "")
    assert "Менеджеры работают Пн–Пт с 10:00 до 22:00 МСК" in welcome_text  # noqa: RUF001


async def test_country_and_city_keyboards_have_flags_and_actions() -> None:
    country_kb = choose_country(get_translator("ru"))
    thailand_cities = choose_city(
        get_translator("ru"),
        [
            SimpleNamespace(id=11, name="Bangkok", country=Country.THAILAND),
            SimpleNamespace(id=12, name="Phuket", country=Country.THAILAND),
        ],
    )
    vietnam_cities = choose_city(
        get_translator("ru"),
        [
            SimpleNamespace(id=21, name="Danang", country=Country.VIETNAM),
            SimpleNamespace(id=22, name="Nha Trang", country=Country.VIETNAM),
            SimpleNamespace(id=23, name="Phu Quoc", country=Country.VIETNAM),
        ],
    )

    assert [button.text for button in country_kb.inline_keyboard[0]] == [
        "🇹🇭 Таиланд",
        "🇻🇳 Вьетнам",
        "🇬🇪 Грузия",
    ]
    assert [button.callback_data for button in country_kb.inline_keyboard[1]] == [
        "menu:orders",
    ]
    assert [button.text for button in thailand_cities.inline_keyboard[0]] == [
        "🇹🇭 Bangkok",
        "🇹🇭 Phuket",
    ]
    assert [button.callback_data for button in thailand_cities.inline_keyboard[0]] == [
        "exchange:city:11",
        "exchange:city:12",
    ]
    assert [button.text for button in thailand_cities.inline_keyboard[1]] == [
        "◀ Назад",
        "❌ Отменить",
    ]
    assert [button.callback_data for button in thailand_cities.inline_keyboard[1]] == [
        "fsm:back",
        "fsm:cancel",
    ]
    assert [button.text for button in vietnam_cities.inline_keyboard[0]] == [
        "🇻🇳 Danang",
        "🇻🇳 Nha Trang",
        "🇻🇳 Phu Quoc",
    ]


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

    await start_handler.cmd_start(message, _FakeState())

    assert len(message.answers) == 1
    reply_markup = message.answers[0]["reply_markup"]
    assert reply_markup.inline_keyboard[0][0].callback_data == "manager:new_orders"
    assert reply_markup.inline_keyboard[1][0].web_app.url == "https://example.com/app"


async def test_manager_new_orders_callback_lists_created_orders(monkeypatch) -> None:
    user = TgUser(
        id=777,
        is_bot=False,
        first_name="Manager",
        username="manager",
        language_code="ru",
    )
    callback = _FakeCallback("manager:new_orders", user)
    fake_db = _FakeDbSession()
    orders = [
        SimpleNamespace(
            id=2,
            publicNumber="2026060002",
            amountSell=10000,
            currencySell="RUB",
            amountBuy=225.5,
            currencyBuy="THB",
        ),
        SimpleNamespace(
            id=1,
            publicNumber="2026060001",
            amountSell=500,
            currencySell="USDT",
            amountBuy=16200,
            currencyBuy="THB",
        ),
    ]

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return (SimpleNamespace(role=2), False)

    class _FakeOrderRepo:
        def __init__(self, db) -> None:
            self.db = db

        async def list_by_status(self, status: int, *, limit: int = 10):
            assert status == 1
            assert limit == 10
            return orders

    monkeypatch.setattr(start_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(start_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(start_handler, "OrderRepository", _FakeOrderRepo)

    await start_handler.manager_new_orders(callback)

    assert callback.message.edits[0]["text"] == get_translator("ru")("manager-new-orders-header")
    reply_markup = callback.message.edits[0]["reply_markup"]
    assert reply_markup.inline_keyboard[0][0].text == "🆕 #2026060002 RUB → THB"
    assert reply_markup.inline_keyboard[0][0].callback_data == "manager:order:2"
    assert reply_markup.inline_keyboard[1][0].text == "🆕 #2026060001 USDT → THB"
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_exchange_keyboards_are_backend_driven() -> None:
    translator = get_translator("ru")

    sell_kb = choose_currency(translator, ["RUB", "USDT", "THB"])
    home_kb = back_to_main_menu(translator)
    amount_kb = amount_controls(translator)
    methods_kb = obtaining(translator, ["cash", "card"])
    confirm_kb = confirm_exchange(translator)
    offline_kb = confirm_off_hours_exchange(translator)

    assert [button.text for button in sell_kb.inline_keyboard[0]] == [
        "🇷🇺 RUB",
        "₮ USDT",
        "🇹🇭 THB",
    ]
    assert home_kb.inline_keyboard[0][0].callback_data == "fsm:cancel"
    assert home_kb.inline_keyboard[0][0].style == "primary"
    assert [button.callback_data for button in amount_kb.inline_keyboard[0]] == [
        "fsm:back",
        "fsm:cancel",
    ]
    assert amount_kb.inline_keyboard[0][0].style == "primary"
    assert amount_kb.inline_keyboard[0][1].style == "danger"
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
    assert [button.text for button in offline_kb.inline_keyboard[0]] == ["✅ Да", "❌ Отмена"]
    assert [button.callback_data for button in offline_kb.inline_keyboard[0]] == [
        "exchange:confirm_offline",
        "fsm:cancel",
    ]
    assert offline_kb.inline_keyboard[0][0].style == "success"
    assert offline_kb.inline_keyboard[0][1].style == "danger"

    created_kb = order_created_actions(translator)
    assert [button.callback_data for button in created_kb.inline_keyboard[0]] == ["menu:orders"]
    assert created_kb.inline_keyboard[0][0].style == "primary"
    assert created_kb.inline_keyboard[1][0].callback_data == "fsm:cancel"
    assert created_kb.inline_keyboard[1][0].style == "primary"


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

    assert len(open_chat.inline_keyboard) == 1
    assert open_chat.inline_keyboard[0][0].callback_data == "op:cancel:17"
    assert open_chat.inline_keyboard[0][0].style == "danger"
    assert open_chat.inline_keyboard[0][1].callback_data == "op:take:17"
    assert open_chat.inline_keyboard[0][1].style == "success"

    assert close_order.inline_keyboard[0][0].text == "💬 Открыть чат с клиентом"  # noqa: RUF001
    assert close_order.inline_keyboard[0][0].url == "https://t.me/customer"
    assert close_order.inline_keyboard[1][0].callback_data == "op:remind:17"
    assert close_order.inline_keyboard[2][0].callback_data == "op:cancel:17"
    assert close_order.inline_keyboard[2][0].style == "danger"
    assert close_order.inline_keyboard[2][1].callback_data == "op:close:17"
    assert close_order.inline_keyboard[2][1].style == "success"
    assert review.inline_keyboard[0][0].url == "https://example.com/review"
    assert review.inline_keyboard[0][0].style == "success"
    assert review.inline_keyboard[1][0].callback_data == "fsm:cancel"
    assert review.inline_keyboard[1][0].style == "primary"


async def test_chat_buttons_open_direct_chat_with_prepared_text() -> None:
    translator = get_translator("ru")

    manager_btn = manager_order_close(
        translator,
        order_id=17,
        chat_url="https://t.me/customer",
        message_text=(
            "Здравствуйте! Вы оставляли заявку #2006877777 на обмен 10 000 USDT. Готовы продолжить?"
        ),
    )
    user_btn = user_order_write_manager(
        translator,
        chat_url="https://t.me/manager",
        message_text=(
            "Здравствуйте! По заявке #367383776 на сумму 5,000 RUB подтверждаю готовность к обмену."
        ),
    )

    manager_url = manager_btn.inline_keyboard[0][0].url
    user_url = user_btn.inline_keyboard[0][0].url
    assert manager_url is not None and user_url is not None

    assert urlparse(manager_url).path == "/customer"
    manager_qs = parse_qs(urlparse(manager_url).query)
    user_qs = parse_qs(urlparse(user_url).query)
    assert manager_qs["text"][0].startswith("Здравствуйте! Вы оставляли заявку #2006877777")
    assert (
        user_qs["text"][0]
        == "Здравствуйте! По заявке #367383776 на сумму 5,000 RUB подтверждаю готовность к обмену."
    )


def test_chat_button_keeps_plain_tg_user_link_without_username() -> None:
    translator = get_translator("ru")

    user_btn = user_order_write_manager(
        translator,
        chat_url="tg://user?id=700002",
        message_text=(
            "Здравствуйте! По заявке #367383776 на сумму 5,000 RUB подтверждаю готовность к обмену."
        ),
    )

    assert user_btn.inline_keyboard[0][0].url == "tg://user?id=700002"
