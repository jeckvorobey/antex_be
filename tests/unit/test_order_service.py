"""Тесты сервиса заявок."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.bank import Bank
from app.models.limitation import Limitation
from app.models.order import Order
from app.models.user import User
from app.services.order import cancel_order


@pytest.mark.asyncio
async def test_cancel_order_restores_qr_limit_with_integer_amount(db_session):
    user = User(
        id=990001,
        username="qr_user",
        first_name="Qr",
        last_name="User",
        language_code="ru",
        is_bot=False,
        role=1,
        is_premium=False,
    )
    bank = Bank(code="QRBANK", name="QR Bank")
    db_session.add_all([user, bank])
    await db_session.flush()

    limitation = Limitation(BankId=bank.id, amount=1000, baseAmount=1000, isActive=True)
    order = Order(
        UserId=user.id,
        BankId=bank.id,
        currencySell="RUB",
        amountSell=5000,
        currencyBuy="USDT",
        amountBuy=55.56,
        rate=1 / 90,
        status=1,
        methodGet="qr",
        createdAt=datetime(2026, 3, 28, 9, 30, tzinfo=UTC),
        updatedAt=datetime(2026, 3, 28, 9, 30, tzinfo=UTC),
    )
    db_session.add_all([limitation, order])
    await db_session.flush()

    await cancel_order(db_session, order.id)

    await db_session.refresh(limitation)
    assert limitation.amount == 1056
