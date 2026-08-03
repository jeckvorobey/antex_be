# ruff: noqa: RUF001
from __future__ import annotations

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import User as TgUser
from sqlalchemy.exc import SQLAlchemyError

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.enums.country import Country
from app.enums.order import OrderStatus
from app.exceptions import AntExException
from app.models.city import City
from app.models.user import User
from app.services.exchange import ExchangePairSnapshot
from app.telegram.handlers import exchange as exchange_handler
from app.telegram.order_cards import OrderMessageView


class _FakeDbSession:
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self.committed = False
        self.rolled_back = False
        self.commit_error = commit_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def test_manager_notification_snapshot_detaches_relationship_values() -> None:
    user = SimpleNamespace(username="customer")
    city = SimpleNamespace(name="Bangkok")
    order = SimpleNamespace(
        id=99,
        publicNumber="202607270001",
        amountSell=15000,
        currencySell="RUB",
        amountBuy=5100,
        currencyBuy="THB",
        rate=0.34,
        methodGet="qrcode",
        country=Country.THAILAND,
        user=user,
        city=city,
    )

    snapshot = exchange_handler._detached_order_snapshot(order)
    user.username = "expired-user"
    city.name = "expired-city"

    view = OrderMessageView.from_order(snapshot)
    assert view.customer_username == "customer"
    assert view.city == "Bangkok"


class _FakeMessage:
    _next_message_id = 1000

    def __init__(self, *, fail_with_not_modified: bool = False) -> None:
        self.edits: list[dict[str, object]] = []
        self.answers: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []
        self.fail_with_not_modified = fail_with_not_modified
        self.message_id = _FakeMessage._next_message_id
        _FakeMessage._next_message_id += 1
        self.chat = SimpleNamespace(id=555001)
        self.bot = _FakeBot()

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edits.append({"text": text, "reply_markup": reply_markup})
        if self.fail_with_not_modified:
            raise TelegramBadRequest(
                method=SimpleNamespace(__api_method__="editMessageText"),
                message=(
                    "Telegram server says - Bad Request: message is not modified: "
                    "specified new message content and reply markup are exactly the same "
                    "as a current content and reply markup of the message"
                ),
            )

    async def answer(self, text: str, reply_markup=None):
        self.answers.append({"text": text, "reply_markup": reply_markup})
        return SimpleNamespace(message_id=self.message_id + len(self.answers))

    async def delete(self) -> None:
        self.deletes.append({"message_id": self.message_id})


class _FakeBot:
    def __init__(self) -> None:
        self.deleted: list[dict[str, object]] = []

    async def delete_message(self, *, chat_id: int, message_id: int) -> None:
        self.deleted.append({"chat_id": chat_id, "message_id": message_id})


class _FakeCallback:
    def __init__(
        self,
        user: TgUser,
        *,
        data: str | None = None,
        fail_with_not_modified: bool = False,
    ) -> None:
        self.from_user = user
        self.data = data
        self.message = _FakeMessage(fail_with_not_modified=fail_with_not_modified)
        self.bot = _FakeBot()
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append({"text": text, "show_alert": show_alert})


class _FakeState:
    def __init__(self, data: dict[str, object]) -> None:
        self._data = data
        self.cleared = False
        self.state: str | None = None

    async def get_data(self) -> dict[str, object]:
        return self._data

    async def update_data(self, **kwargs) -> None:
        self._data.update(kwargs)

    async def set_state(self, state) -> None:
        self.state = getattr(state, "state", state)

    async def get_state(self) -> str | None:
        return self.state

    async def clear(self) -> None:
        self.cleared = True


class _FakeConfigRepository:
    def __init__(self, db) -> None:
        self.db = db

    async def get_or_create(self):
        return SimpleNamespace()


class _WorkingWorkingHoursService:
    def get_availability(self, config):
        return SimpleNamespace(
            status="working",
            schedule_enabled=True,
            working_days_utc=[1, 2, 3, 4, 5],
            start_time_utc=object(),
            end_time_utc=object(),
            business_hours_text="Пн–Пт с 10:00 до 19:00 МСК",
        )


class _OfflineWorkingHoursService:
    def get_availability(self, config):
        return SimpleNamespace(
            status="offline",
            schedule_enabled=True,
            working_days_utc=[1, 2, 3, 4, 5],
            start_time_utc=object(),
            end_time_utc=object(),
            business_hours_text="Пн–Пт с 10:00 до 19:00 МСК",
        )

    def format_business_hours(self, days, start, end, *, locale=None):
        if locale == "en":
            return "Mon–Fri from 10:00 to 19:00 MSK"
        return "Пн–Пт с 10:00 до 19:00 МСК"


def _pair_snapshot(pair_id: str, sell: str, buy: str, rate_text: str) -> ExchangePairSnapshot:
    return ExchangePairSnapshot(
        pair_id=pair_id,
        label=f"{sell}/{buy}",
        currency_sell=sell,
        currency_buy=buy,
        country=Country.THAILAND,
        base_rate=1.0,
        client_rate=1.0,
        calculation_rate=1.0,
        rate_display="1.00",
        rate_text=rate_text,
        amount_sell_example=100,
        amount_buy_example=100.0,
        updated_at=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        available_methods=["qrcode", "cash"],
    )


async def test_render_step_shows_all_loaded_pairs(monkeypatch) -> None:
    callback = _FakeCallback(
        TgUser(
            id=777004,
            is_bot=False,
            first_name="Reader",
            username="reader",
            language_code="ru",
        )
    )
    pairs = [
        _pair_snapshot("rub-thb", "THB", "RUB", "1 THB = 2.51 RUB"),
        _pair_snapshot("usdt-thb", "USDT", "THB", "1 USDT = 35.11 THB"),
        _pair_snapshot("usdt-gel", "USDT", "GEL", "1 USDT = 2.57 GEL"),
        _pair_snapshot("rub-vnd", "RUB", "VND", "1 RUB = 271.60 VND"),
    ]

    async def _fake_get_exchange_pairs():
        return pairs

    monkeypatch.setattr(exchange_handler, "_get_exchange_pairs", _fake_get_exchange_pairs)

    await exchange_handler._render_step(
        actor=callback,
        current=1,
        body="Выберите, что хотите отдать:",
        reply_markup=None,
        edit=True,
    )

    text = str(callback.message.edits[0]["text"])
    assert "Шаг" in text
    assert "1" in text
    assert "5" in text
    assert "🏦 Текущий курс:" not in text
    for pair in pairs:
        assert pair.rate_text not in text
        assert f"({pair.label})" not in text
    assert "🇹🇭 1 THB от 1.00 RUB 🇷🇺" in text
    assert "₮ 1 USDT от 1.00 THB 🇹🇭" in text


async def test_enter_amount_moves_directly_to_confirmation(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    message = _FakeMessage()
    message.from_user = TgUser(
        id=777000,
        is_bot=False,
        first_name="Test",
        username="customer",
        language_code="ru",
    )
    message.text = "15000"
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "currency_buy": "THB",
            "amount_prompt_message_id": 999,
        }
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_get_quote(self, db, payload):
        assert db is fake_db
        assert payload.currency_sell == "RUB"
        assert payload.currency_buy == "THB"
        assert payload.amount_sell == 15000
        return SimpleNamespace(
            currency_sell="RUB",
            currency_buy="THB",
            amount_sell=15000,
            amount_buy=5100.0,
            rate=0.34,
            rate_text="1 RUB = 0.34 THB",
            available_methods=["qrcode", "cash"],
        )

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler.ExchangeService, "get_quote", _fake_get_quote)
    answer_rich_mock = AsyncMock()
    monkeypatch.setattr(exchange_handler, "answer_rich", answer_rich_mock)

    await exchange_handler.enter_amount(message, state)

    assert state.state == exchange_handler.ExchangeState.confirming.state
    assert state._data["amount_sell"] == 15000
    assert state._data["method"] == "qrcode"
    assert state._data["quote"]["amountBuy"] == 5100.0
    answer_rich_mock.assert_awaited_once()
    assert "<table bordered striped>" in answer_rich_mock.await_args.args[1]
    assert message.deletes == [{"message_id": message.message_id}]
    assert message.bot.deleted == [{"chat_id": message.chat.id, "message_id": 999}]


async def test_enter_amount_preserves_selected_cash_method(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    message = _FakeMessage()
    message.from_user = TgUser(
        id=777000,
        is_bot=False,
        first_name="Test",
        username="customer",
        language_code="ru",
    )
    message.text = "25000"
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "currency_buy": "VND",
            "city_id": 11,
            "city_name": "Фукуок",
            "method": "cash",
            "amount_prompt_message_id": 999,
        }
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_get_quote(self, db, payload):
        assert db is fake_db
        assert payload.currency_sell == "RUB"
        assert payload.currency_buy == "VND"
        assert payload.amount_sell == 25000
        return SimpleNamespace(
            currency_sell="RUB",
            currency_buy="VND",
            amount_sell=25000,
            amount_buy=5100.0,
            rate=0.34,
            rate_text="1 RUB = 0.34 VND",
            available_methods=["qrcode", "cash"],
        )

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler.ExchangeService, "get_quote", _fake_get_quote)
    answer_rich_mock = AsyncMock()
    monkeypatch.setattr(exchange_handler, "answer_rich", answer_rich_mock)

    await exchange_handler.enter_amount(message, state)

    assert state.state == exchange_handler.ExchangeState.confirming.state
    assert state._data["method"] == "cash"
    assert state._data["city_id"] == 11
    assert state._data["quote"]["amountBuy"] == 5100.0
    answer_rich_mock.assert_awaited_once()
    assert "<table bordered striped>" in answer_rich_mock.await_args.args[1]
    assert "Фукуок" in answer_rich_mock.await_args.args[1]


async def test_country_sets_buy_currency_and_shows_only_canonical_sell_currencies(
    monkeypatch,
) -> None:
    callback = _FakeCallback(
        TgUser(
            id=777006,
            is_bot=False,
            first_name="Currency",
            username="currency-user",
            language_code="ru",
        )
    )
    state = _FakeState({"country": Country.THAILAND.value})
    pairs = [
        _pair_snapshot("rub-thb", "RUB", "THB", "1 RUB = 0.34 THB"),
        _pair_snapshot("usdt-thb", "USDT", "THB", "1 USDT = 35.11 THB"),
        _pair_snapshot("thb-rub", "THB", "RUB", "1 THB = 2.51 RUB"),
    ]

    async def _fake_get_exchange_pairs(country: str | None = None):
        assert country == Country.THAILAND.value
        return pairs

    edit_mock = AsyncMock()
    monkeypatch.setattr(exchange_handler, "_get_currency_pairs", _fake_get_exchange_pairs)
    monkeypatch.setattr(exchange_handler, "edit_rich", edit_mock)

    await exchange_handler._show_currency_step(callback, state, edit=True)

    assert state.state == exchange_handler.ExchangeState.choosing_currency.state
    assert state._data["currency_buy"] == "THB"
    edit_mock.assert_awaited_once()
    text = edit_mock.await_args.args[1]
    assert "<table" not in text
    assert '<p><tg-emoji emoji-id="6195150966229048345">💰</tg-emoji> 1 USDT' in text
    assert "<p>🇷🇺 1 RUB" in text
    assert "Шаг 4" not in text
    reply_markup = edit_mock.await_args.kwargs["reply_markup"]
    assert [button.callback_data for button in reply_markup.inline_keyboard[0]] == [
        "exchange:currency:USDT",
        "exchange:currency:RUB",
    ]


async def test_currency_pair_loader_keeps_rub_in_exchange_orientation(monkeypatch) -> None:
    """Шаг выбора валюты получает RUB→THB вместо витринной обратной пары THB→RUB."""
    db = _FakeDbSession()
    pairs = [
        _pair_snapshot("rub-thb", "RUB", "THB", "1 RUB = 0.41 THB"),
        _pair_snapshot("usdt-thb", "USDT", "THB", "1 USDT = 30.05 THB"),
    ]
    get_pairs = AsyncMock(return_value=pairs)

    async def _fake_get_db():
        return db

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler.ExchangeService, "list_pair_snapshots", get_pairs)

    result = await exchange_handler._get_currency_pairs(Country.THAILAND.value)

    assert result == pairs
    get_pairs.assert_awaited_once_with(db)


async def test_choose_exchange_currency_moves_directly_to_amount(monkeypatch) -> None:
    callback = _FakeCallback(
        TgUser(
            id=777007,
            is_bot=False,
            first_name="Sell",
            username="sell-user",
            language_code="ru",
        ),
        data="exchange:currency:RUB",
    )
    state = _FakeState({"country": Country.THAILAND.value, "currency_buy": "THB"})

    async def _fake_get_exchange_pairs(country: str | None = None):
        assert country == Country.THAILAND.value
        return [_pair_snapshot("rub-thb", "RUB", "THB", "1 RUB = 0.34 THB")]

    monkeypatch.setattr(exchange_handler, "_get_exchange_pairs", _fake_get_exchange_pairs)
    edit_rich_mock = AsyncMock()
    monkeypatch.setattr(exchange_handler, "edit_rich", edit_rich_mock)

    await exchange_handler.choose_exchange_currency(callback, state)

    assert state.state == exchange_handler.ExchangeState.entering_amount.state
    assert state._data["currency_sell"] == "RUB"
    assert "Введите сумму" in edit_rich_mock.await_args.args[1]
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_choose_exchange_currency_amount_prompt_contains_minimum(monkeypatch) -> None:
    callback = _FakeCallback(
        TgUser(
            id=777023,
            is_bot=False,
            first_name="Minimum",
            username="minimum-user",
            language_code="ru",
        ),
        data="exchange:currency:RUB",
    )
    state = _FakeState(
        {
            "country": Country.THAILAND.value,
            "currency_buy": "THB",
            "method": "qrcode",
        }
    )

    async def _fake_get_exchange_pairs(country: str | None = None):
        assert country == Country.THAILAND.value
        return [_pair_snapshot("rub-thb", "RUB", "THB", "1 RUB = 0.34 THB")]

    monkeypatch.setattr(exchange_handler, "_get_exchange_pairs", _fake_get_exchange_pairs)
    edit_rich_mock = AsyncMock()
    monkeypatch.setattr(exchange_handler, "edit_rich", edit_rich_mock)

    await exchange_handler.choose_exchange_currency(callback, state)

    text = str(edit_rich_mock.await_args.args[1])
    assert "Введите сумму" in text
    assert "Отправьте одним сообщением сумму" in text
    assert "<blockquote>⚠️ Минимальная сумма: «<b>15000 RUB</b>»</blockquote>" in text


async def test_choose_exchange_currency_falls_back_to_direct_pair_rate_for_reversed_display_pairs(
    monkeypatch,
) -> None:
    callback = _FakeCallback(
        TgUser(
            id=777021,
            is_bot=False,
            first_name="Sell",
            username="sell-fallback-user",
            language_code="ru",
        ),
        data="exchange:currency:RUB",
    )
    state = _FakeState({"country": Country.THAILAND.value, "currency_buy": "THB"})
    display_pairs = [_pair_snapshot("thb-rub", "THB", "RUB", "1 THB = 28.50 RUB")]
    rates = [
        SimpleNamespace(
            currency="RUBTHB",
            price=0.035,
            margin=0.0,
            country=Country.THAILAND,
            updatedAt=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        )
    ]

    async def _fake_get_exchange_pairs(country: str | None = None):
        assert country == Country.THAILAND.value
        return display_pairs

    async def _fake_get_db():
        return _FakeDbSession()

    async def _fake_load_rates(self, db):
        return rates

    monkeypatch.setattr(exchange_handler, "_get_exchange_pairs", _fake_get_exchange_pairs)
    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler.ExchangeService, "load_rates", _fake_load_rates)

    await exchange_handler.choose_exchange_currency(callback, state)

    assert state.state == exchange_handler.ExchangeState.entering_amount.state
    text = str(callback.message.edits[0]["text"])
    assert "1 RUB" in text
    assert "THB" in text
    assert "1 THB = 28.50 RUB" not in text
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_choose_exchange_currency_falls_back_to_direct_pair_rate_for_georgia(
    monkeypatch,
) -> None:
    callback = _FakeCallback(
        TgUser(
            id=777022,
            is_bot=False,
            first_name="Sell",
            username="sell-fallback-georgia",
            language_code="ru",
        ),
        data="exchange:currency:RUB",
    )
    state = _FakeState({"country": Country.GEORGIA.value, "currency_buy": "GEL"})
    display_pairs = [_pair_snapshot("gel-rub", "GEL", "RUB", "1 GEL = 31.00 RUB")]
    rates = [
        SimpleNamespace(
            currency="RUBGEL",
            price=0.0325,
            margin=0.0,
            country=Country.GEORGIA,
            updatedAt=datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
        )
    ]

    async def _fake_get_exchange_pairs(country: str | None = None):
        assert country == Country.GEORGIA.value
        return display_pairs

    async def _fake_get_db():
        return _FakeDbSession()

    async def _fake_load_rates(self, db):
        return rates

    monkeypatch.setattr(exchange_handler, "_get_exchange_pairs", _fake_get_exchange_pairs)
    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler.ExchangeService, "load_rates", _fake_load_rates)

    await exchange_handler.choose_exchange_currency(callback, state)

    assert state.state == exchange_handler.ExchangeState.entering_amount.state
    text = str(callback.message.edits[0]["text"])
    assert "1 RUB" in text
    assert "GEL" in text
    assert "1 GEL = 31.00 RUB" not in text
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_fsm_back_from_currency_returns_to_service_step() -> None:
    callback = _FakeCallback(
        TgUser(
            id=777019,
            is_bot=False,
            first_name="Back",
            username="back-currency-user",
            language_code="ru",
        )
    )
    state = _FakeState({"country": Country.THAILAND.value})
    state.state = exchange_handler.ExchangeState.choosing_currency.state

    await exchange_handler.fsm_back(callback, state)

    assert state.state == exchange_handler.ExchangeState.choosing_service.state
    assert "<b>💠 Выберите подходящую услугу</b>" in str(callback.message.edits[0]["text"])
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_fsm_back_from_city_returns_to_service_step() -> None:
    callback = _FakeCallback(
        TgUser(
            id=777020,
            is_bot=False,
            first_name="Back",
            username="back-city-user",
            language_code="ru",
        )
    )
    state = _FakeState({"country": Country.THAILAND.value, "service_label": "cash_delivery"})
    state.state = exchange_handler.ExchangeState.choosing_city.state

    await exchange_handler.fsm_back(callback, state)

    assert state.state == exchange_handler.ExchangeState.choosing_service.state
    assert "<b>💠 Выберите подходящую услугу</b>" in str(callback.message.edits[0]["text"])
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_fsm_back_from_service_returns_to_country_step(monkeypatch) -> None:
    callback = _FakeCallback(
        TgUser(
            id=777018,
            is_bot=False,
            first_name="Back",
            username="back-service-user",
            language_code="ru",
        )
    )
    state = _FakeState({"country": Country.THAILAND.value})
    state.state = exchange_handler.ExchangeState.choosing_service.state

    async def _fake_get_exchange_pairs(country: str | None = None):
        assert country is None
        return []

    monkeypatch.setattr(exchange_handler, "_get_exchange_pairs", _fake_get_exchange_pairs)

    await exchange_handler.fsm_back(callback, state)

    assert state.state == exchange_handler.ExchangeState.choosing_country.state
    assert "<b>AntEx</b>" in str(callback.message.edits[0]["text"])
    assert "выберите страну в списке ниже" in str(callback.message.edits[0]["text"])
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_fsm_back_from_amount_returns_to_sell_currency_step(monkeypatch) -> None:
    callback = _FakeCallback(
        TgUser(
            id=777008,
            is_bot=False,
            first_name="Back",
            username="back-user",
            language_code="ru",
        )
    )
    state = _FakeState(
        {
            "country": Country.THAILAND.value,
            "currency_sell": "RUB",
            "currency_buy": "THB",
            "pair_snapshots": [
                _pair_snapshot("rub-thb", "RUB", "THB", "1 RUB = 0.34 THB"),
                _pair_snapshot("usdt-thb", "USDT", "THB", "1 USDT = 35.11 THB"),
            ],
        }
    )
    state.state = exchange_handler.ExchangeState.entering_amount.state
    pairs = [
        _pair_snapshot("rub-thb", "RUB", "THB", "1 RUB = 0.34 THB"),
        _pair_snapshot("usdt-thb", "USDT", "THB", "1 USDT = 35.11 THB"),
    ]

    async def _fake_get_exchange_pairs(country: str | None = None):
        assert country == Country.THAILAND.value
        return pairs

    monkeypatch.setattr(exchange_handler, "_get_currency_pairs", _fake_get_exchange_pairs)

    await exchange_handler.fsm_back(callback, state)

    assert state.state == exchange_handler.ExchangeState.choosing_currency.state
    assert "Выберите валюту, которую хотите обменять" in str(callback.message.edits[0]["text"])
    reply_markup = callback.message.edits[0]["reply_markup"]
    assert [button.callback_data for button in reply_markup.inline_keyboard[0]] == [
        "exchange:currency:USDT",
        "exchange:currency:RUB",
    ]
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_enter_amount_rejects_below_minimum_and_stays_on_amount_step(monkeypatch) -> None:
    message = _FakeMessage()
    message.from_user = TgUser(
        id=777024,
        is_bot=False,
        first_name="Minimum",
        username="minimum-user",
        language_code="ru",
    )
    message.text = "14999"
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "currency_buy": "THB",
            "method": "qrcode",
            "amount_prompt_message_id": 999,
        }
    )
    quote_mock = AsyncMock()
    monkeypatch.setattr(exchange_handler.ExchangeService, "get_quote", quote_mock)

    await exchange_handler.enter_amount(message, state)

    assert state.state == exchange_handler.ExchangeState.entering_amount.state
    assert state._data.get("amount_sell") is None
    assert len(message.answers) == 1
    assert message.answers[0]["text"] == (
        "Сумма должна быть не меньше 15000. Введите допустимую сумму для данного способа получения."
    )
    assert message.answers[0]["reply_markup"] is not None
    quote_mock.assert_not_called()


async def test_enter_amount_rejects_non_positive_amount_and_stays_on_amount_step(
    monkeypatch,
) -> None:
    message = _FakeMessage()
    message.from_user = TgUser(
        id=777025,
        is_bot=False,
        first_name="Invalid",
        username="invalid-user",
        language_code="ru",
    )
    message.text = "0"
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "currency_buy": "THB",
            "method": "qrcode",
        }
    )
    quote_mock = AsyncMock()
    monkeypatch.setattr(exchange_handler.ExchangeService, "get_quote", quote_mock)

    await exchange_handler.enter_amount(message, state)

    assert state.state is None
    assert len(message.answers) == 1
    assert message.answers[0]["text"] == "Укажите сумму числом, больше нуля."
    quote_mock.assert_not_called()


async def test_confirm_exchange_warns_before_creating_order_when_managers_offline(
    monkeypatch,
) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback(
        TgUser(
            id=777026,
            is_bot=False,
            first_name="Offline",
            username="offline-user",
            language_code="ru",
        )
    )
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "amount_sell": 15000,
            "currency_buy": "THB",
            "quote": {
                "amountBuy": 5100,
                "rate": 0.34,
                "rateText": "1 RUB = 0.34 THB",
            },
            "method": "qrcode",
            "country": Country.THAILAND.value,
        }
    )
    create_mock = AsyncMock()

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return User(
            id=25,
            telegram_id=777026,
            username="offline-user",
            first_name="Offline",
            role=3,
        ), False

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "ConfigRepository", _FakeConfigRepository)
    monkeypatch.setattr(exchange_handler, "ManagerWorkingHoursService", _OfflineWorkingHoursService)
    monkeypatch.setattr(exchange_handler, "create_order_for_user", create_mock)

    await exchange_handler.confirm_exchange_callback(callback, state)

    create_mock.assert_not_called()
    assert state.cleared is False
    assert state._data.get("off_hours_confirmed") is None
    assert callback.answers[-1] == {
        "text": "Менеджер обработает заявку утром после начала рабочего дня.",
        "show_alert": True,
    }
    assert "⚠️ Менеджеры сейчас не работают" in callback.message.edits[0]["text"]
    assert "Пн–Пт с 10:00 до 19:00 МСК" in callback.message.edits[0]["text"]
    reply_markup = callback.message.edits[0]["reply_markup"]
    assert [button.callback_data for button in reply_markup.inline_keyboard[0]] == [
        "exchange:confirm_offline",
        "fsm:cancel",
    ]


async def test_confirm_exchange_localizes_off_hours_schedule_for_english_user(
    monkeypatch,
) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback(
        TgUser(
            id=777028,
            is_bot=False,
            first_name="English",
            username="english-user",
            language_code="en",
        )
    )
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "amount_sell": 15000,
            "currency_buy": "THB",
            "quote": {
                "amountBuy": 5100,
                "rate": 0.34,
                "rateText": "1 RUB = 0.34 THB",
            },
            "method": "qrcode",
            "country": Country.THAILAND.value,
        }
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return User(
            id=28,
            telegram_id=777028,
            username="english-user",
            first_name="English",
            role=3,
        ), False

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "ConfigRepository", _FakeConfigRepository)
    monkeypatch.setattr(exchange_handler, "ManagerWorkingHoursService", _OfflineWorkingHoursService)
    monkeypatch.setattr(exchange_handler, "create_order_for_user", AsyncMock())

    await exchange_handler.confirm_exchange_callback(callback, state)

    assert "Managers are not working right now" in callback.message.edits[0]["text"]
    assert "Mon–Fri from 10:00 to 19:00 MSK" in callback.message.edits[0]["text"]
    assert "Пн–Пт" not in callback.message.edits[0]["text"]


async def test_confirm_offline_exchange_creates_order_after_warning(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    user = User(
        id=26,
        telegram_id=777027,
        username="confirmed-user",
        first_name="Confirmed",
        role=3,
    )
    created_order = SimpleNamespace(
        id=101,
        publicNumber="202607270101",
        amountSell=15000,
        currencySell="RUB",
        amountBuy=5100.0,
        currencyBuy="THB",
        methodGet="qrcode",
        status=int(OrderStatus.CREATED),
        manager_availability=SimpleNamespace(status="offline"),
    )
    callback = _FakeCallback(
        TgUser(
            id=777027,
            is_bot=False,
            first_name="Confirmed",
            username="confirmed-user",
            language_code="ru",
        )
    )
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "amount_sell": 15000,
            "currency_buy": "THB",
            "quote": {
                "amountBuy": 5100,
                "rate": 0.34,
                "rateText": "1 RUB = 0.34 THB",
            },
            "method": "qrcode",
            "country": Country.THAILAND.value,
        }
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return user, False

    async def _fake_create_order_for_user(
        db,
        current_user,
        payload,
        *,
        notify_user=True,
        defer_notifications=False,
    ):
        assert current_user is user
        assert payload.amount_sell == 15000
        assert notify_user is False
        assert defer_notifications is True
        return created_order

    manager_notification = AsyncMock()

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "ConfigRepository", _FakeConfigRepository)
    monkeypatch.setattr(exchange_handler, "ManagerWorkingHoursService", _OfflineWorkingHoursService)
    monkeypatch.setattr(exchange_handler, "create_order_for_user", _fake_create_order_for_user)
    monkeypatch.setattr(
        exchange_handler,
        "_notify_manager_order_created",
        manager_notification,
    )

    await exchange_handler.confirm_offline_exchange_callback(callback, state)

    assert state.cleared is True
    assert "Заявка #202607270101 создана" in callback.message.answers[0]["text"].replace(
        "\u2068", ""
    ).replace("\u2069", "")
    assert "<blockquote>Менеджер обработает заявку утром" in callback.message.answers[0]["text"]
    manager_notification.assert_awaited_once_with(fake_db, created_order, user)


async def test_confirm_exchange_creates_order_with_default_qrcode(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    city = City(id=11, name="Bangkok", country=Country.THAILAND)
    user = User(
        id=22,
        telegram_id=777001,
        username="customer",
        first_name="Test",
        role=3,
        city_id=city.id,
    )
    created_order = SimpleNamespace(
        id=99,
        publicNumber="202607270001",
        amountSell=15000,
        currencySell="RUB",
        amountBuy=5100.0,
        currencyBuy="THB",
        methodGet="qrcode",
        status=int(OrderStatus.CREATED),
        manager_availability=SimpleNamespace(status="offline"),
    )
    callback = _FakeCallback(
        TgUser(
            id=777001,
            is_bot=False,
            first_name="Test",
            username="customer",
            language_code="ru",
        )
    )
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "amount_sell": 15000,
            "currency_buy": "THB",
            "quote": {
                "amountBuy": 5100,
                "rate": 0.34,
                "rateText": "1 RUB = 0.34 THB",
            },
            "method": "qrcode",
        }
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return user, False

    async def _fake_create_order_for_user(
        db,
        current_user,
        payload,
        *,
        notify_user=True,
        defer_notifications=False,
    ):
        assert db is fake_db
        assert current_user is user
        assert payload.city_id is None
        assert payload.country == Country.THAILAND
        assert payload.currency_sell == "RUB"
        assert payload.currency_buy == "THB"
        assert payload.amount_sell == 15000
        assert payload.amount_buy == 5100
        assert payload.rate == 0.34
        assert payload.method_get == "qrcode"
        assert notify_user is False
        assert defer_notifications is True
        return created_order

    manager_notification = AsyncMock()

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "ConfigRepository", _FakeConfigRepository)
    monkeypatch.setattr(exchange_handler, "ManagerWorkingHoursService", _WorkingWorkingHoursService)
    monkeypatch.setattr(exchange_handler, "create_order_for_user", _fake_create_order_for_user)
    monkeypatch.setattr(
        exchange_handler,
        "_notify_manager_order_created",
        manager_notification,
    )

    await exchange_handler.confirm_exchange_callback(callback, state)

    assert state.cleared is True
    assert fake_db.committed is True
    assert created_order.userNotificationMessageId == callback.message.message_id + 1
    manager_notification.assert_awaited_once_with(fake_db, created_order, user)
    assert len(callback.message.edits) == 0
    assert callback.message.deletes == [{"message_id": callback.message.message_id}]
    assert len(callback.message.answers) == 1
    assert "после начала рабочего дня" in callback.message.answers[0]["text"]
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_confirm_exchange_does_not_repeat_created_order_when_message_id_commit_fails(
    monkeypatch,
) -> None:
    fake_db = _FakeDbSession(commit_error=SQLAlchemyError("write unavailable"))
    user = User(
        id=22,
        telegram_id=777001,
        username="customer",
        first_name="Test",
        role=3,
    )
    created_order = SimpleNamespace(
        id=99,
        publicNumber="202607270001",
        status=int(OrderStatus.CREATED),
        manager_availability=SimpleNamespace(status="working"),
    )
    callback = _FakeCallback(
        TgUser(
            id=777001,
            is_bot=False,
            first_name="Test",
            username="customer",
            language_code="ru",
        )
    )
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "amount_sell": 15000,
            "currency_buy": "THB",
            "quote": {"amountBuy": 5100, "rate": 0.34},
            "method": "qrcode",
            "country": Country.THAILAND.value,
        }
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return user, False

    async def _fake_create_order_for_user(db, current_user, payload, **kwargs):
        return created_order

    manager_notification = AsyncMock()

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "ConfigRepository", _FakeConfigRepository)
    monkeypatch.setattr(exchange_handler, "ManagerWorkingHoursService", _WorkingWorkingHoursService)
    monkeypatch.setattr(exchange_handler, "create_order_for_user", _fake_create_order_for_user)
    monkeypatch.setattr(
        exchange_handler,
        "_notify_manager_order_created",
        manager_notification,
    )

    await exchange_handler.confirm_exchange_callback(callback, state)

    assert state.cleared is True
    assert fake_db.rolled_back is True
    assert callback.answers[-1] == {"text": None, "show_alert": False}
    manager_notification.assert_awaited_once()
    notification_db, notification_order, notification_user = manager_notification.await_args.args
    assert notification_db is fake_db
    assert notification_order.id == created_order.id
    assert notification_order.publicNumber == created_order.publicNumber
    assert notification_user.id == user.id
    assert notification_user.telegram_id == user.telegram_id
    assert notification_user.username == user.username


async def test_confirm_exchange_notifies_manager_when_initial_customer_card_fails(
    monkeypatch,
) -> None:
    fake_db = _FakeDbSession()
    user = User(
        id=22,
        telegram_id=777001,
        username="customer",
        first_name="Test",
        role=3,
    )
    created_order = SimpleNamespace(
        id=99,
        publicNumber="202607270001",
        status=int(OrderStatus.CREATED),
        manager_availability=SimpleNamespace(status="working"),
    )
    callback = _FakeCallback(
        TgUser(
            id=777001,
            is_bot=False,
            first_name="Test",
            username="customer",
            language_code="ru",
        )
    )
    callback.message.answer = AsyncMock(side_effect=RuntimeError("Telegram unavailable"))
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "amount_sell": 15000,
            "currency_buy": "THB",
            "quote": {"amountBuy": 5100, "rate": 0.34},
            "method": "qrcode",
            "country": Country.THAILAND.value,
        }
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return user, False

    async def _fake_create_order_for_user(db, current_user, payload, **kwargs):
        return created_order

    manager_notification = AsyncMock()

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "ConfigRepository", _FakeConfigRepository)
    monkeypatch.setattr(exchange_handler, "ManagerWorkingHoursService", _WorkingWorkingHoursService)
    monkeypatch.setattr(exchange_handler, "create_order_for_user", _fake_create_order_for_user)
    monkeypatch.setattr(
        exchange_handler,
        "_notify_manager_order_created",
        manager_notification,
    )

    await exchange_handler.confirm_exchange_callback(callback, state)

    assert state.cleared is True
    assert callback.answers[-1]["show_alert"] is True
    assert "202607270001" in callback.answers[-1]["text"]
    manager_notification.assert_awaited_once_with(fake_db, created_order, user)


async def test_confirm_exchange_shows_human_error_on_order_creation_failure(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    user = User(
        id=24,
        telegram_id=777003,
        username="customer",
        first_name="Test",
        role=3,
    )
    callback = _FakeCallback(
        TgUser(
            id=777003,
            is_bot=False,
            first_name="Test",
            username="customer",
            language_code="ru",
        )
    )
    state = _FakeState(
        {
            "currency_sell": "RUB",
            "amount_sell": 15000,
            "currency_buy": "THB",
            "quote": {
                "amountBuy": 5100,
                "rate": 0.34,
                "rateText": "1 RUB = 0.34 THB",
            },
            "method": "qrcode",
        }
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return user, False

    async def _fake_create_order_for_user(
        db,
        current_user,
        payload,
        *,
        notify_user=True,
        defer_notifications=False,
    ):
        assert notify_user is False
        assert defer_notifications is True
        raise AntExException(
            "User has reached active orders limit",
            code="ORDER_ALREADY_EXISTS",
            status_code=409,
        )

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "ConfigRepository", _FakeConfigRepository)
    monkeypatch.setattr(exchange_handler, "ManagerWorkingHoursService", _WorkingWorkingHoursService)
    monkeypatch.setattr(exchange_handler, "create_order_for_user", _fake_create_order_for_user)

    await exchange_handler.confirm_exchange_callback(callback, state)

    assert state.cleared is False
    assert callback.answers[-1]["show_alert"] is True
    assert callback.answers[-1]["text"] is not None


async def test_menu_orders_renders_compact_order_history(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback(
        TgUser(
            id=777006,
            is_bot=False,
            first_name="Orders",
            username="orders-user",
            language_code="ru",
        )
    )
    user = User(
        id=24,
        telegram_id=777006,
        username="orders-user",
        first_name="Orders",
        role=3,
    )
    order = SimpleNamespace(
        id=11,
        publicNumber="2026060011",
        status=int(OrderStatus.CREATED),
        amountSell=1400,
        currencySell="USDT",
        amountBuy=35738752.0,
        currencyBuy="VND",
        rate=25527.68,
        methodGet="cash",
        createdAt=datetime(2026, 6, 13, 0, 45, tzinfo=UTC),
        updatedAt=None,
        endTime=None,
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        assert db is fake_db
        assert tg_user.id == 777006
        return user, False

    class _FakeOrderRepository:
        def __init__(self, db) -> None:
            self.db = db

        async def count_user_orders(self, user_id: int):
            assert self.db is fake_db
            assert user_id == 24
            return 1

        async def get_user_orders(self, user_id: int, limit: int = 10, offset: int = 0):
            assert self.db is fake_db
            assert user_id == 24
            assert limit == 10
            assert offset == 0
            return [order]

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "OrderRepository", _FakeOrderRepository)

    await exchange_handler.menu_orders(callback)

    text = str(callback.message.edits[0]["text"])
    assert "Ваши заявки:" in text
    assert "#2026060011: Новая" in text
    assert "1,400 ₮ USDT → 35,738,752.0 🇻🇳 VND" in text
    assert "Курс: 25527.68" in text
    assert "Способ получения: Доставка наличных" in text
    assert "13.06.2026 00:45 UTC" in text
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_menu_orders_commits_new_user_and_ignores_not_modified(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback(
        TgUser(
            id=777002,
            is_bot=False,
            first_name="Repeat",
            username="repeat-user",
            language_code="ru",
        ),
        fail_with_not_modified=True,
    )
    user = User(
        id=23,
        telegram_id=777002,
        username="repeat-user",
        first_name="Repeat",
        role=3,
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        assert db is fake_db
        assert tg_user.id == 777002
        return user, True

    class _FakeOrderRepository:
        def __init__(self, db) -> None:
            self.db = db

        async def count_user_orders(self, user_id: int):
            assert self.db is fake_db
            assert user_id == 23
            return 0

        async def get_user_orders(self, user_id: int, limit: int = 10, offset: int = 0):
            assert self.db is fake_db
            assert user_id == 23
            assert limit == 10
            assert offset == 0
            return []

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "OrderRepository", _FakeOrderRepository)

    await exchange_handler.menu_orders(callback)

    assert fake_db.committed is True
    assert len(callback.message.edits) == 1
    reply_markup = callback.message.edits[0]["reply_markup"]
    assert reply_markup.inline_keyboard[0][0].callback_data == "fsm:cancel"
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_fsm_cancel_returns_to_country_step() -> None:
    callback = _FakeCallback(
        TgUser(
            id=777005,
            is_bot=False,
            first_name="Cancel",
            username="cancel-user",
            language_code="ru",
        )
    )
    state = _FakeState({"currency_sell": "RUB"})
    state.state = exchange_handler.ExchangeState.entering_amount.state

    await exchange_handler.fsm_cancel(callback, state)

    assert state.cleared is True
    assert state.state == exchange_handler.ExchangeState.choosing_country.state
    assert len(callback.message.edits) == 1
    text = str(callback.message.edits[0]["text"])
    assert "<b>AntEx</b>" in text
    assert "выберите страну в списке ниже" in text
    reply_markup = callback.message.edits[0]["reply_markup"]
    assert [button.callback_data for button in reply_markup.inline_keyboard[0]] == [
        "exchange:country:thailand",
        "exchange:country:vietnam",
        "exchange:country:georgia",
    ]
    assert reply_markup.inline_keyboard[1][0].callback_data == "menu:orders"
    assert callback.answers[-1] == {"text": None, "show_alert": False}


async def test_show_city_step_edits_as_rich_message_without_step_counter(monkeypatch) -> None:
    callback = _FakeCallback(
        TgUser(
            id=777030,
            is_bot=False,
            first_name="City",
            username="city-user",
            language_code="ru",
        )
    )
    state = _FakeState(
        {"country": Country.VIETNAM.value, "service_label": "cash_delivery"}
    )
    city = SimpleNamespace(id=17, name="Дананг")

    class _Result:
        def scalars(self):
            return SimpleNamespace(all=lambda: [city])

    fake_db = _FakeDbSession()
    fake_db.execute = AsyncMock(return_value=_Result())
    edit_mock = AsyncMock()

    async def _fake_get_db():
        return fake_db

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "edit_rich", edit_mock)

    await exchange_handler._show_city_step(callback, state, edit=True)

    assert state.state == exchange_handler.ExchangeState.choosing_city.state
    edit_mock.assert_awaited_once()
    text = edit_mock.await_args.args[1]
    assert "<h2>📍 Выберите город</h2>" in text
    assert "Шаг 3" not in text
    assert edit_mock.await_args.kwargs["reply_markup"].inline_keyboard[0][0].text == "Дананг"
