from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.country import Country
from app.enums.user import UserRole
from app.models.city import City
from app.models.rate import Rate
from app.models.user import User
from app.schemas.miniapp import MiniappOrderCreate
from app.services import order_flow


@pytest.mark.asyncio
async def test_create_order_for_user_passes_global_manager_to_notification(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    city = City(name="Bangkok", country=Country.THAILAND)
    manager = User(
        telegram_id=700001,
        username="manager",
        first_name="Order",
        role=int(UserRole.MANAGER),
    )
    customer = User(
        telegram_id=700002,
        username="customer",
        first_name="Happy",
        role=int(UserRole.USER),
    )
    rate = Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND)

    db_session.add_all([city, manager, customer, rate])
    await db_session.flush()

    customer.city_id = city.id
    await db_session.commit()

    notify_mock = AsyncMock()
    monkeypatch.setattr(order_flow, "notify_order_created", notify_mock)

    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        cityId=city.id,
        currencySell="RUB",
        amountSell=10000,
        currencyBuy="THB",
        amountBuy=4000,
        rate=0.4,
        methodGet="cash",
    )

    await order_flow.create_order_for_user(db_session, customer, payload)

    notify_mock.assert_awaited_once()
    _, _, notified_manager = notify_mock.await_args.args
    assert notified_manager is not None
    assert notified_manager.id == manager.id
