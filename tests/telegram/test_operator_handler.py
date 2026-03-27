"""Тесты operator handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.enums.user import UserRole
from app.telegram.handlers import operator


class DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def commit(self) -> None:
        return None


def make_db_generator(session: DummySession):
    async def fake_get_db_session():
        yield session

    return fake_get_db_session


@pytest.mark.asyncio
async def test_operator_confirm_denies_non_operator(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
) -> None:
    callback = SimpleNamespace(
        data="op:confirm:1",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_message.bot,
        answer=AsyncMock(),
    )

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(role=UserRole.USER), False

    monkeypatch.setattr(operator, "get_db_session", make_db_generator(DummySession()))
    monkeypatch.setattr(operator, "check_user", fake_check_user)

    await operator.operator_confirm(callback)
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_operator_confirm_updates_status_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
) -> None:
    mock_message.text = "Order text"
    callback = SimpleNamespace(
        data="op:confirm:5",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_message.bot,
        answer=AsyncMock(),
    )
    order = SimpleNamespace(UserId=77)

    class DummyOrderRepo:
        def __init__(self, session) -> None:
            del session

        async def get_one(self, order_id: int):
            assert order_id == 5
            return order

        async def update_status(self, order_id: int, status: int):
            assert order_id == 5
            assert status == 2
            return order

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(role=UserRole.OPERATOR), False

    notify_user = AsyncMock()
    monkeypatch.setattr(operator, "get_db_session", make_db_generator(DummySession()))
    monkeypatch.setattr(operator, "check_user", fake_check_user)
    monkeypatch.setattr(operator, "OrderRepository", DummyOrderRepo)
    monkeypatch.setattr(operator, "notify_user", notify_user)

    await operator.operator_confirm(callback)

    notify_user.assert_awaited_once()
    assert mock_message.bot.last_message is not None


@pytest.mark.asyncio
async def test_operator_cancel_updates_status_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
) -> None:
    mock_message.text = "Order text"
    callback = SimpleNamespace(
        data="op:cancel:5",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_message.bot,
        answer=AsyncMock(),
    )
    order = SimpleNamespace(UserId=77)

    class DummyOrderRepo:
        def __init__(self, session) -> None:
            del session

        async def get_one(self, order_id: int):
            assert order_id == 5
            return order

        async def cancel(self, order_id: int):
            assert order_id == 5
            return order

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(role=UserRole.OPERATOR), False

    notify_user = AsyncMock()
    monkeypatch.setattr(operator, "get_db_session", make_db_generator(DummySession()))
    monkeypatch.setattr(operator, "check_user", fake_check_user)
    monkeypatch.setattr(operator, "OrderRepository", DummyOrderRepo)
    monkeypatch.setattr(operator, "notify_user", notify_user)

    await operator.operator_cancel(callback)

    notify_user.assert_awaited_once()
    assert mock_message.bot.last_message is not None
