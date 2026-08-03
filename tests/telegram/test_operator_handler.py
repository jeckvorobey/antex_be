from __future__ import annotations

# ruff: noqa: RUF001
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import User as TgUser

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.enums.order import OrderStatus
from app.services.order_notifications import DeliveryOutcome
from app.services.order_status import OrderTakeResult
from app.telegram.handlers import operator as operator_handler


class _FakeDbSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeMessage:
    def __init__(self) -> None:
        self.edits: list[dict[str, object]] = []

    async def edit_text(
        self,
        text: str | None = None,
        rich_message=None,
        reply_markup=None,
    ) -> None:
        self.edits.append(
            {"text": text, "rich_message": rich_message, "reply_markup": reply_markup}
        )

    async def edit_reply_markup(self, reply_markup=None) -> None:
        self.edits.append({"text": None, "rich_message": None, "reply_markup": reply_markup})


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


async def test_operator_take_moves_order_to_processing(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback("op:take:5")
    updated_order = SimpleNamespace(
        id=5,
        publicNumber="2026050001",
        status=int(OrderStatus.PROCESSING),
        city=SimpleNamespace(name="Bangkok"),
        user=SimpleNamespace(username="customer", telegram_id=700002),
        currencySell="RUB",
        currencyBuy="THB",
        amountSell=10000,
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    class _FakeOrderRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_one(self, order_id: int):
            assert order_id == 5
            return SimpleNamespace(status=int(OrderStatus.CREATED))

    async def _fake_take_order_in_work(db, *, order_id: int):
        assert order_id == 5
        return OrderTakeResult(order=updated_order, delivery=DeliveryOutcome.RICH)

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(operator_handler, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(operator_handler, "take_order_in_work", _fake_take_order_in_work)

    await operator_handler.operator_take(callback)

    assert callback.answers[-1] == {
        "text": None,
        "show_alert": False,
        "url": None,
    }
    assert (
        callback.message.edits[0]["reply_markup"].inline_keyboard[2][0].callback_data
        == "op:cancel:5"
    )
    assert (
        callback.message.edits[0]["reply_markup"].inline_keyboard[2][1].callback_data
        == "op:close:5"
    )
    chat_url = callback.message.edits[0]["reply_markup"].inline_keyboard[0][0].url
    assert chat_url is not None
    assert chat_url.startswith("https://t.me/customer?text=")
    rich_html = callback.message.edits[0]["rich_message"].html
    assert "✅ Заявка #2026050001 принята в работу" in rich_html
    assert "Клиенту отправлена просьба начать диалог" in rich_html
    assert "<table bordered striped>" in rich_html


async def test_operator_take_shows_honest_failed_delivery_state(monkeypatch) -> None:
    callback = _FakeCallback("op:take:5")
    order = SimpleNamespace(
        id=5,
        publicNumber="2026050001",
        status=int(OrderStatus.PROCESSING),
        user=SimpleNamespace(username="customer", telegram_id=700002),
        currencySell="RUB",
        currencyBuy="THB",
        amountSell=10000,
    )

    class _FakeOrderRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_one(self, order_id: int):
            return SimpleNamespace(status=int(OrderStatus.CREATED))

    async def _fake_get_db():
        return _FakeDbSession()

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    async def _fake_take_order_in_work(db, *, order_id: int):
        return OrderTakeResult(order=order, delivery=DeliveryOutcome.FAILED)

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(operator_handler, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(operator_handler, "take_order_in_work", _fake_take_order_in_work)

    await operator_handler.operator_take(callback)

    rich_html = callback.message.edits[0]["rich_message"].html
    assert "сообщение клиенту не доставлено" in rich_html
    assert "Клиенту отправлена просьба" not in rich_html
    assert callback.answers[-1]["show_alert"] is True
    assert "клиенту не удалось отправить" in callback.answers[-1]["text"]


async def test_operator_take_rejects_stale_callback(monkeypatch) -> None:
    callback = _FakeCallback("op:take:5")
    take_order = AsyncMock()

    class _FakeOrderRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_one(self, order_id: int):
            return SimpleNamespace(status=int(OrderStatus.PROCESSING))

    async def _fake_get_db():
        return _FakeDbSession()

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(operator_handler, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(operator_handler, "take_order_in_work", take_order)

    await operator_handler.operator_take(callback)

    take_order.assert_not_awaited()
    assert callback.message.edits == []
    assert callback.answers[-1]["text"] == "Заявка уже изменила статус"


async def test_operator_take_preserves_operator_access_control(monkeypatch) -> None:
    callback = _FakeCallback("op:take:5")

    async def _fake_get_db():
        return _FakeDbSession()

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=9), False

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)

    await operator_handler.operator_take(callback)

    assert callback.message.edits == []
    assert callback.answers[-1] == {"text": "Нет прав", "show_alert": True, "url": None}


@pytest.mark.parametrize(
    ("delivery", "show_alert", "answer"),
    [
        (DeliveryOutcome.RICH, False, "🔔 Напоминание отправлено клиенту"),
        (DeliveryOutcome.FALLBACK, False, "🔔 Напоминание отправлено клиенту"),
        (DeliveryOutcome.FAILED, True, "Не удалось отправить напоминание. Попробуйте ещё раз."),
    ],
)
async def test_operator_remind_reports_actual_delivery(
    monkeypatch,
    delivery: DeliveryOutcome,
    show_alert: bool,
    answer: str,
) -> None:
    callback = _FakeCallback("op:remind:5")
    order = SimpleNamespace(id=5, status=int(OrderStatus.PROCESSING))
    manager = SimpleNamespace(id=7, username="manager")
    reminder = AsyncMock(return_value=delivery)

    class _FakeOrderRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_one(self, order_id: int):
            return order

    class _FakeUserRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_manager(self):
            return manager

    async def _fake_get_db():
        return _FakeDbSession()

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(operator_handler, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(operator_handler, "UserRepository", _FakeUserRepository)
    monkeypatch.setattr(operator_handler, "send_customer_reminder", reminder)

    await operator_handler.operator_remind(callback)

    reminder.assert_awaited_once_with(order, manager)
    assert callback.answers[-1] == {"text": answer, "show_alert": show_alert, "url": None}


@pytest.mark.parametrize(
    ("order", "answer"),
    [
        (None, "Заявка не найдена"),
        (
            SimpleNamespace(id=5, status=int(OrderStatus.CREATED)),
            "Напоминание доступно только для заявки в работе",
        ),
    ],
)
async def test_operator_remind_rejects_missing_or_inactive_order(
    monkeypatch,
    order,
    answer: str,
) -> None:
    callback = _FakeCallback("op:remind:5")
    reminder = AsyncMock()

    class _FakeOrderRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_one(self, order_id: int):
            return order

    async def _fake_get_db():
        return _FakeDbSession()

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(operator_handler, "OrderRepository", _FakeOrderRepository)
    monkeypatch.setattr(operator_handler, "send_customer_reminder", reminder)

    await operator_handler.operator_remind(callback)

    reminder.assert_not_awaited()
    assert callback.answers[-1] == {"text": answer, "show_alert": True, "url": None}


async def test_operator_open_chat_handler_is_no_longer_used(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback("op:open_chat:5")

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)

    await operator_handler.operator_open_chat(callback)

    assert callback.answers[-1] == {
        "text": "Кнопка чата устарела",
        "show_alert": True,
        "url": None,
    }
    assert callback.message.edits == []


async def test_operator_cancel_requests_confirmation(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback("op:cancel:9")

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)

    await operator_handler.operator_cancel(callback)

    assert callback.answers[-1] == {
        "text": None,
        "show_alert": False,
        "url": None,
    }
    markup = callback.message.edits[0]["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == "op:cancel_confirm:9"
    assert markup.inline_keyboard[1][0].callback_data == "op:cancel_keep:9"


async def test_operator_cancel_confirm_marks_order_cancelled(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback("op:cancel_confirm:9")
    updated_order = SimpleNamespace(
        id=9,
        publicNumber="2026050002",
        status=int(OrderStatus.CANCELLED),
        city=SimpleNamespace(name="Bangkok"),
        user=SimpleNamespace(username="customer", telegram_id=700002),
        currencySell="RUB",
        currencyBuy="THB",
        amountSell=25000,
        methodGet="cash",
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    async def _fake_update_order_status(db, *, order_id: int, status):
        assert order_id == 9
        assert status == OrderStatus.CANCELLED
        return updated_order

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(operator_handler, "update_order_status", _fake_update_order_status)

    await operator_handler.operator_cancel_confirm(callback)

    assert callback.answers[-1] == {"text": "Заявка отменена", "show_alert": True, "url": None}
    assert (
        callback.message.edits[0]["reply_markup"].inline_keyboard[0][0].url
        == "https://t.me/customer"
    )
    rich_html = callback.message.edits[0]["rich_message"].html
    assert "❌ Заявка #2026050002 отменена" in rich_html
    assert "Работа по заявке остановлена" in rich_html


async def test_operator_cancel_keep_restores_processing_keyboard(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback("op:cancel_keep:9")
    order = SimpleNamespace(
        id=9,
        publicNumber="2026050002",
        status=int(OrderStatus.PROCESSING),
        user=SimpleNamespace(username="customer", telegram_id=700002),
        currencySell="USDT",
        amountSell=1500,
    )

    async def _fake_get_db():
        return fake_db

    async def _fake_check_user(db, tg_user):
        return SimpleNamespace(role=2), False

    class _FakeOrderRepository:
        def __init__(self, session) -> None:
            self.session = session

        async def get_one(self, order_id: int):
            assert order_id == 9
            return order

    monkeypatch.setattr(operator_handler, "_get_db", _fake_get_db)
    monkeypatch.setattr(operator_handler, "check_user", _fake_check_user)
    monkeypatch.setattr(operator_handler, "OrderRepository", _FakeOrderRepository)

    await operator_handler.operator_cancel_keep(callback)

    assert callback.answers[-1] == {"text": None, "show_alert": False, "url": None}
    markup = callback.message.edits[0]["reply_markup"]
    assert markup.inline_keyboard[2][0].callback_data == "op:cancel:9"
    assert markup.inline_keyboard[2][1].callback_data == "op:close:9"
    chat_url = markup.inline_keyboard[0][0].url
    assert chat_url is not None
    assert chat_url.startswith("https://t.me/customer?text=")


async def test_operator_close_marks_order_completed(monkeypatch) -> None:
    fake_db = _FakeDbSession()
    callback = _FakeCallback("op:close:9")
    updated_order = SimpleNamespace(
        id=9,
        publicNumber="2026050002",
        status=int(OrderStatus.COMPLETED),
        country=SimpleNamespace(value="georgia"),
        city=SimpleNamespace(name="Батуми"),
        rate=2.71,
        user=SimpleNamespace(username="customer", telegram_id=700002),
        currencySell="USDT",
        currencyBuy="GEL",
        amountSell=10000,
        amountBuy=27100,
        methodGet="cash",
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
    assert (
        callback.message.edits[0]["reply_markup"].inline_keyboard[0][0].url
        == "https://t.me/customer"
    )
    text = str(callback.message.edits[0]["rich_message"].html)
    assert "✅ Заявка #2026050002 завершена" in text
    assert "Страна</td><td><b>Грузия" in text
    assert "Город</td><td><b>Батуми" in text
    assert "Курс</td><td><b>2.71" in text
    assert "Отдаёте</td><td><b>10 000 ₮ USDT" in text
    assert "Получаете</td><td><b>27 100 🇬🇪 GEL" in text
    assert "Способ получения</td><td><b>Доставка наличных" in text
    assert "Обмен успешно выполнен" in text
