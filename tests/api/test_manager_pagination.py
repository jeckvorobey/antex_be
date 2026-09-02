"""Проверки полного пути пагинации и серверных прав менеджера."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.user import UserRole
from app.models.chat import ChatConversation, ChatMessage
from app.models.order import Order
from app.models.user import User


@pytest.fixture
async def manager_client(db_session, monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "jwt_secret", "manager-pagination-secret-at-least-32-bytes")
    manager = User(telegram_id=950001, role=int(UserRole.MANAGER))
    db_session.add(manager)
    await db_session.commit()

    async def database():
        yield db_session

    app.dependency_overrides[deps.get_db_session] = database
    token = create_access_token({"sub": str(manager.id), "type": "user"})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, manager
    finally:
        app.dependency_overrides.clear()


async def test_orders_pages_reach_every_active_order_and_aggregate_all(db_session, manager_client):
    client, manager = manager_client
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    orders = [
        Order(
            UserId=manager.id,
            country=Country.THAILAND,
            currencySell="RUB",
            amountSell=100,
            currencyBuy="THB",
            amountBuy=40,
            status=1 if i % 2 else 2,
            methodGet="cash",
            publicNumber=f"PAGE{i:05}",
            createdAt=today if i < 10 else today - timedelta(days=1),
        )
        for i in range(205)
    ]
    orders.extend(
        [
            Order(
                UserId=manager.id,
                country=Country.THAILAND,
                currencySell="RUB",
                amountSell=999,
                currencyBuy="THB",
                status=3,
                methodGet="cash",
                publicNumber="FINAL",
            ),
            Order(
                UserId=manager.id,
                country=Country.THAILAND,
                currencySell="RUB",
                amountSell=999,
                currencyBuy="THB",
                status=1,
                methodGet="cash",
                destroyTime=today,
                publicNumber="DELETED",
            ),
        ]
    )
    db_session.add_all(orders)
    await db_session.commit()
    seen = []
    for offset in range(0, 250, 50):
        response = await client.get(
            "/api/manager/orders",
            params={
                "limit": 50,
                "offset": offset,
                "todayFrom": today.isoformat(),
            },
        )
        assert response.status_code == 200
        page = response.json()
        assert len(page["items"]) == min(50, 205 - offset)
        assert page["total"] == 205
        assert page["todayTotal"] == 10
        assert page["amountTotals"] == {"RUB": 20500}
        seen.extend(item["id"] for item in page["items"])
    expected = sorted(orders[:205], key=lambda row: (row.createdAt, row.id), reverse=True)
    assert seen == [row.id for row in expected]
    assert len(set(seen)) == 205
    assert (await client.get("/api/manager/orders", params={"offset": 205})).json()["items"] == []


@pytest.mark.parametrize("path", ["orders", "chats"])
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_invalid_list_pagination_is_rejected(manager_client, path, params):
    client, _ = manager_client
    assert (await client.get(f"/api/manager/{path}", params=params)).status_code == 422


async def test_chat_pages_and_message_cursor_are_complete(db_session, manager_client):
    client, manager = manager_client
    users = [User(telegram_id=951000 + i, first_name="Страница") for i in range(103)]
    db_session.add_all(users)
    await db_session.flush()
    chats = [
        ChatConversation(user_id=user.id, manager_id=manager.id, unread_count=i % 2)
        for i, user in enumerate(users)
    ]
    db_session.add_all(chats)
    await db_session.flush()
    messages = [
        ChatMessage(
            conversation_id=chats[0].id,
            direction="inbound",
            message_type="text",
            text=str(i),
            telegram_chat_id=users[0].telegram_id,
            delivery_status="received",
        )
        for i in range(103)
    ]
    db_session.add_all(messages)
    await db_session.commit()
    seen = []
    for offset in (0, 50, 100):
        page = (
            await client.get("/api/manager/chats", params={"limit": 50, "offset": offset})
        ).json()
        assert page["total"] == 103
        assert len(page["items"]) == min(50, 103 - offset)
        seen.extend(item["id"] for item in page["items"])
    assert len(set(seen)) == 103
    params = {"limit": 50}
    seen_messages = []
    for has_more in (True, True, False):
        page = (
            await client.get(f"/api/manager/chats/{chats[0].id}/messages", params=params)
        ).json()
        assert page["hasMore"] is has_more
        ids = [item["id"] for item in page["items"]]
        assert ids == sorted(ids)
        seen_messages = ids + seen_messages
        params["beforeId"] = ids[0]
    assert seen_messages == [message.id for message in messages]


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/manager/chats"),
        ("GET", "/api/manager/chats/1"),
        ("GET", "/api/manager/chats/1/messages"),
        ("POST", "/api/manager/chats/1/read"),
        ("POST", "/api/manager/chats/1/close"),
        ("GET", "/api/manager/orders"),
        ("GET", "/api/manager/orders/1"),
        ("POST", "/api/manager/orders/1/chat"),
        ("PATCH", "/api/manager/orders/1/status"),
        ("POST", "/api/manager/chats/1/messages"),
        ("POST", "/api/manager/chats/1/forward"),
        ("GET", "/api/manager/chat-attachments/1"),
        ("POST", "/api/manager/chats/1/attachments"),
        ("POST", "/api/manager/chats/1/attachments/test/retry"),
        ("GET", "/api/manager/realtime/stream"),
        ("PUT", "/api/manager/realtime/viewing"),
    ],
)
async def test_manager_routes_ignore_forged_role_and_revoke_access(
    db_session,
    manager_client,
    method,
    path,
):
    client, manager = manager_client
    token = create_access_token({"sub": str(manager.id), "role": 2, "type": "user"})
    manager.role = int(UserRole.USER)
    await db_session.commit()
    response = await client.request(
        method,
        path,
        params={"role": 2},
        headers={"Authorization": f"Bearer {token}", "X-Role": "2"},
        json={"role": 2},
    )
    assert response.status_code == 403
