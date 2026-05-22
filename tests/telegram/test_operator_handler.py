from __future__ import annotations

# ruff: noqa: RUF001
import os
from types import SimpleNamespace

from aiogram.types import User as TgUser

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.enums.order import OrderStatus
from app.telegram.handlers import operator as operator_handler


class _FakeDbSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeMessage:
    def __init__(self) -> None:
        self.edits: list[dict[str, object]] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edits.append({"text": text, "reply_markup": reply_markup})


class _FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = TgUser(
            id=777001,
            is_bot=False,
            first_name="Manager",
            username="manager",
            language_code="ru",
        )
        self.message = _FakeMessage()
        self.answers: list[dict[str, object]] = []

    async def answer(
        self,
        text: str | None = None,
        show_alert: bool = False,
        url: str | None = None,
    ) -> None:
        self.answers.append({"text": text, "show_alert": show_alert, "url": url})


async def test_operator_open_chat_moves_order_to_processing(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback("op:open_chat:5")
    initial_order = SimpleNamespace(
        id=5,
        user=SimpleNamespace(username="customer", telegram_id=700002),
    )
    updated_order = SimpleNamespace(
        id=5,
        publicNumber="2026050001",
        status=int(OrderStatus.PROCESSING),
        city=SimpleNamespace(name="Bangkok"),
        currencySell="RUB",
        currencyBuy="THB",
        amountSell=10000,
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    class _FakeOrderRepository:
        def __init__(self, db) -> None:
            self.db = db

        async def get_one(self, order_id: int):
            assert order_id == 5
            return initial_order

    async def _fake_update_order_status(db, *, order_id: int, status):
        assert order_id == 5
        assert status == OrderStatus.PROCESSING
        return updated_order

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(operator_handler, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(operator_handler, "update_order_status", _fake_update_order_status)
    monkeypatch.setattr(operator_handler, "build_manager_chat_url", lambda order: "https://t.me/customer")

    await operator_handler.operator_open_chat(callback)

    assert callback.answers[-1] == {
        "text": None,
        "show_alert": False,
        "url": "https://t.me/customer",
    }
    assert (
        callback.message.edits[0]["reply_markup"].inline_keyboard[0][0].callback_data
        == "op:close:5"
    )
    assert "В работе" in callback.message.edits[0]["text"]


async def test_operator_close_marks_order_completed(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback("op:close:9")
    updated_order = SimpleNamespace(
        id=9,
        publicNumber="2026050002",
        status=int(OrderStatus.COMPLETED),
        city=SimpleNamespace(name="Bangkok"),
        currencySell="RUB",
        currencyBuy="THB",
        amountSell=25000,
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    async def _fake_update_order_status(db, *, order_id: int, status):
        assert order_id == 9
        assert status == OrderStatus.COMPLETED
        return updated_order

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(operator_handler, "update_order_status", _fake_update_order_status)

    await operator_handler.operator_close(callback)

    assert callback.answers[-1] == {"text": None, "show_alert": False, "url": None}
    assert callback.message.edits[0]["reply_markup"] is None
    assert "Завершена" in callback.message.edits[0]["text"]
