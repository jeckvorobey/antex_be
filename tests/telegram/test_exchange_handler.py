from __future__ import annotations

import os
from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import User as TgUser

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.enums.country import Country
from app.enums.order import OrderStatus
from app.models.city import City
from app.models.user import User
from app.telegram.handlers import exchange as exchange_handler


class _FakeDbSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        self.committed = True


class _FakeMessage:
    def __init__(self, *, fail_with_not_modified: bool = False) -> None:
        self.edits: list[dict[str, object]] = []
        self.fail_with_not_modified = fail_with_not_modified

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


class _FakeBot:
    pass


class _FakeCallback:
    def __init__(self, user: TgUser, *, fail_with_not_modified: bool = False) -> None:
        self.from_user = user
        self.message = _FakeMessage(fail_with_not_modified=fail_with_not_modified)
        self.bot = _FakeBot()
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answers.append({"text": text, "show_alert": show_alert})


class _FakeState:
    def __init__(self, data: dict[str, object]) -> None:
        self._data = data
        self.cleared = False

    async def get_data(self) -> dict[str, object]:
        return self._data

    async def clear(self) -> None:
        self.cleared = True


async def test_confirm_exchange_creates_order_without_bank_dependency(monkeypatch) -> None:
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
        amountSell=15000,
        currencySell="RUB",
        amountBuy=5100.0,
        currencyBuy="THB",
        methodGet="cash",
        status=int(OrderStatus.CREATED),
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
            },
            "method": "cash",
        }
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return user, False

    async def _fake_create_order_for_user(db, current_user, payload):
        assert db is fake_db
        assert current_user is user
        assert payload.city_id == city.id
        assert payload.country == Country.THAILAND
        assert payload.currency_sell == "RUB"
        assert payload.currency_buy == "THB"
        assert payload.amount_sell == 15000
        assert payload.amount_buy == 5100
        assert payload.rate == 0.34
        assert payload.method_get == "cash"
        return created_order

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "create_order_for_user", _fake_create_order_for_user)

    await exchange_handler.confirm_exchange_callback(callback, state)

    assert state.cleared is True
    assert fake_db.committed is False
    assert len(callback.message.edits) == 1
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

        async def get_user_orders(self, user_id: int):
            assert self.db is fake_db
            assert user_id == 23
            return []

    monkeypatch.setattr(exchange_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(exchange_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(exchange_handler, "OrderRepository", _FakeOrderRepository)

    await exchange_handler.menu_orders(callback)

    assert fake_db.committed is True
    assert len(callback.message.edits) == 1
    assert callback.answers[-1] == {"text": None, "show_alert": False}
