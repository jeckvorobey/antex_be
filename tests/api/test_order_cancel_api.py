"""API-тесты пользовательской отмены заявки (POST /api/orders/{id}/cancel)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.order import OrderStatus
from app.enums.user import UserRole
from app.models.order import Order
from app.models.user import User
from app.services import order_status

ORDER_PAYLOAD = {
    "country": "thailand",
    "currencySell": "rub",
    "amountSell": 30000,
    "currencyBuy": "thb",
    "amountBuy": 12000,
    "rate": 0.4,
    "methodGet": "qrcode",
}


@pytest.fixture
async def api_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession]]:
    from app.main import app
    from app.services import order_flow

    settings.jwt_secret = "test-secret-for-order-cancel"
    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session

    app.dependency_overrides.clear()


async def seed_exchange_data(db_session: AsyncSession) -> tuple[User, User]:
    from app.enums.country import Country
    from app.models.city import City
    from app.models.rate import Rate

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
    stranger = User(
        telegram_id=700003,
        username="stranger",
        first_name="Other",
        role=int(UserRole.USER),
    )
    db_session.add_all(
        [
            city,
            manager,
            customer,
            stranger,
            Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND),
            Rate(currency="USDTTHB", price=36.2, margin=3.0, country=Country.THAILAND),
        ]
    )
    await db_session.flush()

    manager.city_id = city.id
    customer.city_id = city.id
    await db_session.flush()
    return customer, stranger


async def create_order_for(
    client: AsyncClient,
    user: User,
    db_session: AsyncSession,
) -> Order:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json=ORDER_PAYLOAD,
    )
    assert response.status_code == 201, response.text
    order = await db_session.scalar(
        select(Order).where(Order.UserId == user.id).order_by(Order.id.desc())
    )
    assert order is not None
    return order


@pytest.mark.asyncio
async def test_user_cancels_created_order(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    customer, _ = await seed_exchange_data(db_session)
    sync_mock = AsyncMock()
    monkeypatch.setattr(order_status, "enqueue_order_telegram_sync_tasks", sync_mock)
    order = await create_order_for(client, customer, db_session)

    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    response = await client.post(
        f"/api/orders/{order.id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == order.id
    assert payload["status"] == int(OrderStatus.CANCELLED)
    sync_mock.assert_awaited_once()

    refreshed = await db_session.scalar(select(Order).where(Order.id == order.id))
    assert refreshed is not None
    assert refreshed.status == int(OrderStatus.CANCELLED)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup_statuses", "expected_status"),
    [
        ((OrderStatus.PROCESSING,), OrderStatus.PROCESSING),
        ((OrderStatus.PROCESSING, OrderStatus.COMPLETED), OrderStatus.COMPLETED),
        ((OrderStatus.CANCELLED,), OrderStatus.CANCELLED),
    ],
)
async def test_user_cannot_cancel_non_created_order(
    setup_statuses: tuple[OrderStatus, ...],
    expected_status: OrderStatus,
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    from app.services.order_status import update_order_status

    customer, _ = await seed_exchange_data(db_session)
    monkeypatch.setattr(order_status, "enqueue_order_telegram_sync_tasks", AsyncMock())
    order = await create_order_for(client, customer, db_session)
    for next_status in setup_statuses:
        await update_order_status(db_session, order_id=order.id, status=next_status)

    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    response = await client.post(
        f"/api/orders/{order.id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ORDER_STATUS_CONFLICT"
    refreshed = await db_session.scalar(select(Order).where(Order.id == order.id))
    assert refreshed is not None
    assert refreshed.status == int(expected_status)


@pytest.mark.asyncio
async def test_user_cannot_cancel_foreign_order(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    customer, stranger = await seed_exchange_data(db_session)
    monkeypatch.setattr(order_status, "enqueue_order_telegram_sync_tasks", AsyncMock())
    order = await create_order_for(client, customer, db_session)

    token = create_access_token({"sub": str(stranger.id), "role": stranger.role})
    response = await client.post(
        f"/api/orders/{order.id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    refreshed = await db_session.scalar(select(Order).where(Order.id == order.id))
    assert refreshed is not None
    assert refreshed.status == int(OrderStatus.CREATED)


@pytest.mark.asyncio
async def test_manager_cancel_of_processing_order_is_still_allowed(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    from app.services.order_status import update_order_status

    customer, _ = await seed_exchange_data(db_session)
    monkeypatch.setattr(order_status, "enqueue_order_telegram_sync_tasks", AsyncMock())
    order = await create_order_for(client, customer, db_session)
    await update_order_status(
        db_session,
        order_id=order.id,
        status=OrderStatus.PROCESSING,
    )

    updated = await update_order_status(
        db_session,
        order_id=order.id,
        status=OrderStatus.CANCELLED,
    )

    assert updated.status == int(OrderStatus.CANCELLED)
