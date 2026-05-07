from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.user import UserRole
from app.models.city import City
from app.models.rate import Rate
from app.models.user import User


@pytest.fixture
async def api_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession]]:
    from app.core.config import settings
    from app.main import app
    from app.services import auth as auth_service
    from app.services import order_flow

    settings.jwt_secret = "test-secret-for-happy-path-checks"
    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())
    monkeypatch.setattr(
        auth_service,
        "validate_telegram_init_data",
        lambda _: {
            "user": json.dumps(
                {
                    "id": 123456,
                    "username": "telegram_user",
                    "first_name": "Tele",
                    "last_name": "Gram",
                    "language_code": "ru",
                    "is_bot": False,
                    "is_premium": True,
                }
            )
        },
    )

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_returns_ok(api_client: tuple[AsyncClient, AsyncSession]) -> None:
    client, _ = api_client

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "AntEx"}


@pytest.mark.asyncio
async def test_telegram_auth_returns_token_and_allows_get_me(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client

    auth_response = await client.post(
        "/api/auth/telegram",
        json={"init_data": "stub"},
    )

    assert auth_response.status_code == 200
    payload = auth_response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]

    me_response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["username"] == "telegram_user"

    stored_user = await db_session.get(User, 1)
    assert stored_user is not None
    assert stored_user.telegram_id == 123456


@pytest.mark.asyncio
async def test_rates_and_order_happy_path(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client

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
    rate = Rate(currency="RUBTHB", price=0.41)

    db_session.add_all([city, manager, customer, rate])
    await db_session.flush()

    manager.city_id = city.id
    await db_session.flush()

    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    rates_response = await client.get("/api/miniapp/rates")

    assert rates_response.status_code == 200
    assert rates_response.json()["items"][0]["currency"] == "RUBTHB"

    create_response = await client.post(
        "/api/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "CityId": city.id,
            "currencySell": "rub",
            "amountSell": 10000,
            "currencyBuy": "thb",
            "amountBuy": 4100,
            "rate": 0.41,
            "address": "Sukhumvit",
            "contactTelegram": "@customer",
            "methodGet": "cash",
        },
    )

    assert create_response.status_code == 201
    created_order = create_response.json()
    assert created_order["currencySell"] == "RUB"
    assert created_order["currencyBuy"] == "THB"
    assert created_order["CityId"] == city.id

    order_id = created_order["id"]

    list_response = await client.get(
        "/api/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == order_id

    detail_response = await client.get(
        f"/api/orders/{order_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["address"] == "Sukhumvit"
