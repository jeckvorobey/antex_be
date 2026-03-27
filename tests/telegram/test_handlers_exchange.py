"""TDD тесты для exchange flow handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.telegram.handlers import exchange
from app.telegram.handlers.exchange import ExchangeState


@pytest.mark.asyncio
async def test_currency_message_contains_progress(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    monkeypatch.setattr(exchange.messages, "exchange_step", lambda *args, **kwargs: "Step 1/4")
    monkeypatch.setattr(exchange.messages, "exchange_rate", lambda *args, **kwargs: "Rate")
    monkeypatch.setattr(
        exchange.messages,
        "choose_currency_prompt",
        lambda *args, **kwargs: "Выберите валюту",
    )

    callback = SimpleNamespace(
        data="menu:exchange",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )

    await exchange.menu_exchange(callback, mock_state)

    sent = mock_bot.last_message
    assert sent is not None
    assert any(x in sent.text for x in ["1/4", "1 из 4", "Шаг 1"])


@pytest.mark.asyncio
async def test_confirm_message_shows_amount_and_currency(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    await mock_state.set_data(
        {
            "amount_sell": 10000,
            "currency_sell": "RUB",
            "amount_buy": 4200,
            "method": "qr",
        }
    )
    monkeypatch.setattr(
        exchange.messages,
        "exchange_confirm_summary",
        lambda **kwargs: (
            f"Шаг 4 из 4\n"
            f"{kwargs['amount']} {kwargs['from_currency']}\n"
            f"{kwargs['result']} {kwargs['to_currency']}"
        ),
    )

    callback = SimpleNamespace(
        data="method:qr",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )

    async def fake_get_db_session():
        yield None

    monkeypatch.setattr(exchange, "get_db_session", fake_get_db_session)
    monkeypatch.setattr(exchange, "AllowanceRepository", lambda session: None)
    monkeypatch.setattr(exchange, "BankRepository", lambda session: None)

    await mock_state.set_state(ExchangeState.confirming)
    await exchange.show_confirmation(callback, mock_state)

    sent = mock_bot.last_message
    assert sent is not None
    assert "10000" in sent.text or "10 000" in sent.text
    assert "THB" in sent.text


@pytest.mark.asyncio
async def test_fsm_back_restores_previous_state(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    monkeypatch.setattr(exchange.messages, "exchange_step", lambda *args, **kwargs: "Step 2/4")
    monkeypatch.setattr(exchange.messages, "exchange_rate", lambda *args, **kwargs: "Rate")
    monkeypatch.setattr(
        exchange.messages,
        "enter_amount_prompt",
        lambda *args, **kwargs: "Enter amount",
    )

    callback = SimpleNamespace(
        data="fsm:back",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )

    await mock_state.set_data({"currency_sell": "RUB"})
    await mock_state.set_state(ExchangeState.choosing_method)

    await exchange.fsm_back(callback, mock_state)

    state = await mock_state.get_state()
    assert state == ExchangeState.entering_amount.state


@pytest.mark.asyncio
async def test_fsm_cancel_clears_state(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    monkeypatch.setattr(exchange.messages, "home_title", lambda *args, **kwargs: "Главное меню")
    callback = SimpleNamespace(
        data="fsm:cancel",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )

    await mock_state.set_state(ExchangeState.confirming)
    await exchange.fsm_cancel(callback, mock_state)

    assert await mock_state.get_state() is None


@pytest.mark.asyncio
async def test_no_message_sent_without_keyboard(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    monkeypatch.setattr(exchange.messages, "exchange_step", lambda *args, **kwargs: "Step")
    monkeypatch.setattr(exchange.messages, "exchange_rate", lambda *args, **kwargs: "Rate")
    monkeypatch.setattr(
        exchange.messages,
        "choose_currency_prompt",
        lambda *args, **kwargs: "Currency",
    )
    callback = SimpleNamespace(
        data="menu:exchange",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )

    await exchange.menu_exchange(callback, mock_state)

    for msg in mock_bot.sent_messages:
        if msg.from_exchange_flow:
            assert msg.reply_markup is not None, f"Message missing keyboard: {msg.text[:40]}"


@pytest.mark.asyncio
async def test_menu_orders_renders_empty_state(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
) -> None:
    callback = SimpleNamespace(
        data="menu:orders",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    async def fake_get_db():
        return DummySession()

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(id=1), False

    class DummyOrderRepo:
        def __init__(self, session) -> None:
            del session

        async def get_user_orders(self, user_id: int):
            assert user_id == 1
            return []

    monkeypatch.setattr(exchange, "_get_db", fake_get_db)
    monkeypatch.setattr(exchange, "check_user", fake_check_user)
    monkeypatch.setattr(exchange, "OrderRepository", DummyOrderRepo)

    await exchange.menu_orders(callback)

    assert mock_bot.last_message is not None
    assert mock_bot.last_message.reply_markup is not None


@pytest.mark.asyncio
async def test_choose_exchange_currency_sets_state_and_renders_step(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    monkeypatch.setattr(exchange, "_get_rate_snapshot", AsyncMock(return_value=(0.42, 33.0)))
    callback = SimpleNamespace(
        data="exchange:currency:RUB",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )

    await mock_state.set_state(ExchangeState.choosing_currency)
    await exchange.choose_exchange_currency(callback, mock_state)

    assert await mock_state.get_state() == ExchangeState.entering_amount.state
    assert mock_bot.last_message is not None


@pytest.mark.asyncio
async def test_enter_amount_invalid_shows_error(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
    mock_state,
) -> None:
    monkeypatch.setattr(exchange, "_get_rate_snapshot", AsyncMock(return_value=(0.42, 33.0)))
    mock_message.text = "0"

    await mock_state.set_state(ExchangeState.entering_amount)
    await exchange.enter_amount(mock_message, mock_state)

    assert mock_message.bot.last_message is not None
    assert mock_message.bot.last_message.reply_markup is not None


@pytest.mark.asyncio
async def test_enter_amount_valid_moves_to_method_selection(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
    mock_state,
) -> None:
    monkeypatch.setattr(exchange, "_get_rate_snapshot", AsyncMock(return_value=(0.42, 33.0)))
    mock_message.text = "1500"

    await mock_state.set_state(ExchangeState.entering_amount)
    await exchange.enter_amount(mock_message, mock_state)

    assert await mock_state.get_state() == ExchangeState.choosing_method.state
    assert mock_message.bot.last_message is not None
    assert mock_message.bot.last_message.reply_markup is not None


@pytest.mark.asyncio
async def test_choose_method_sets_confirming_and_delegates_to_show_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    callback = SimpleNamespace(
        data="method:cash",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )
    show_confirmation = AsyncMock()
    monkeypatch.setattr(exchange, "_get_rate_snapshot", AsyncMock(return_value=(0.5, 33.0)))
    monkeypatch.setattr(exchange, "show_confirmation", show_confirmation)

    await mock_state.set_data({"amount_sell": 1000, "currency_sell": "RUB"})
    await mock_state.set_state(ExchangeState.choosing_method)
    await exchange.choose_method(callback, mock_state)

    assert await mock_state.get_state() == ExchangeState.confirming.state
    show_confirmation.assert_awaited_once_with(callback, mock_state)


@pytest.mark.asyncio
async def test_confirm_exchange_creates_order_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    callback = SimpleNamespace(
        data="exchange:confirm",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def commit(self) -> None:
            return None

    async def fake_get_db():
        return DummySession()

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(id=77), False

    class DummyBankRepo:
        def __init__(self, session) -> None:
            del session

        async def get_all(self):
            return [SimpleNamespace(id=10)]

    created_order = SimpleNamespace(
        id=1,
        amountSell=1000,
        currencySell="RUB",
        amountBuy=2000,
        currencyBuy="THB",
    )

    class DummyOrderRepo:
        def __init__(self, session) -> None:
            del session

        async def create(self, **kwargs):
            assert kwargs["UserId"] == 77
            return created_order

    notify_operator = AsyncMock()
    monkeypatch.setattr(exchange, "_get_db", fake_get_db)
    monkeypatch.setattr(exchange, "check_user", fake_check_user)
    monkeypatch.setattr(exchange, "BankRepository", DummyBankRepo)
    monkeypatch.setattr(exchange, "OrderRepository", DummyOrderRepo)
    monkeypatch.setattr(exchange, "notify_operator", notify_operator)

    await mock_state.set_data(
        {
            "currency_sell": "RUB",
            "amount_sell": 1000,
            "amount_buy": 2000,
            "rate": 0.5,
            "method": "cash",
        }
    )
    await mock_state.set_state(ExchangeState.confirming)
    await exchange.confirm_exchange_callback(callback, mock_state)

    assert await mock_state.get_state() is None
    notify_operator.assert_awaited_once()


@pytest.mark.asyncio
async def test_choose_method_blocks_when_rate_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    callback = SimpleNamespace(
        data="method:cash",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )
    show_confirmation = AsyncMock()
    monkeypatch.setattr(exchange, "_get_rate_snapshot", AsyncMock(return_value=(0.0, 0.0)))
    monkeypatch.setattr(exchange, "show_confirmation", show_confirmation)

    await mock_state.set_data({"amount_sell": 1000, "currency_sell": "RUB"})
    await mock_state.set_state(ExchangeState.choosing_method)
    await exchange.choose_method(callback, mock_state)

    assert await mock_state.get_state() == ExchangeState.choosing_method.state
    show_confirmation.assert_not_called()
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_confirm_exchange_blocks_when_rate_invalid(
    monkeypatch: pytest.MonkeyPatch,
    mock_bot,
    mock_message,
    mock_state,
) -> None:
    callback = SimpleNamespace(
        data="exchange:confirm",
        message=mock_message,
        from_user=mock_message.from_user,
        bot=mock_bot,
        answer=AsyncMock(),
    )

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def commit(self) -> None:
            raise AssertionError("commit must not be called for invalid rate")

    async def fake_get_db():
        return DummySession()

    create = AsyncMock()
    monkeypatch.setattr(exchange, "_get_db", fake_get_db)
    monkeypatch.setattr(exchange, "check_user", AsyncMock())
    monkeypatch.setattr(exchange, "BankRepository", AsyncMock())
    monkeypatch.setattr(exchange, "OrderRepository", lambda session: SimpleNamespace(create=create))
    monkeypatch.setattr(exchange, "notify_operator", AsyncMock())

    await mock_state.set_data(
        {
            "currency_sell": "RUB",
            "amount_sell": 1000,
            "amount_buy": 0,
            "rate": 0.0,
            "method": "cash",
        }
    )
    await mock_state.set_state(ExchangeState.confirming)
    await exchange.confirm_exchange_callback(callback, mock_state)

    assert await mock_state.get_state() == ExchangeState.confirming.state
    create.assert_not_called()
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_legacy_exchange_text_entry_still_works(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
    mock_state,
) -> None:
    monkeypatch.setattr(exchange, "_get_rate_snapshot", AsyncMock(return_value=(0.42, 33.0)))
    mock_message.text = "💱 Обмен"

    await exchange.legacy_menu_exchange(mock_message, mock_state)

    assert await mock_state.get_state() == ExchangeState.choosing_currency.state
    assert mock_message.bot.last_message is not None
    callbacks = [
        btn.callback_data
        for row in mock_message.bot.last_message.reply_markup.inline_keyboard
        for btn in row
    ]
    assert "exchange:currency:RUB" in callbacks


@pytest.mark.asyncio
async def test_legacy_orders_text_entry_still_works(
    monkeypatch: pytest.MonkeyPatch,
    mock_message,
) -> None:
    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

    async def fake_get_db():
        return DummySession()

    async def fake_check_user(db, from_user):
        del db, from_user
        return SimpleNamespace(id=1), False

    class DummyOrderRepo:
        def __init__(self, session) -> None:
            del session

        async def get_user_orders(self, user_id: int):
            assert user_id == 1
            return []

    monkeypatch.setattr(exchange, "_get_db", fake_get_db)
    monkeypatch.setattr(exchange, "check_user", fake_check_user)
    monkeypatch.setattr(exchange, "OrderRepository", DummyOrderRepo)
    mock_message.text = "📋 Мои заявки"

    await exchange.legacy_menu_orders(mock_message)

    assert mock_message.bot.last_message is not None
    assert mock_message.bot.last_message.reply_markup is not None
