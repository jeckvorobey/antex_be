from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.api.routers import manager as manager_router
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.user import UserRole
from app.models.user import User


class FakeRealtimeHub:
    def __init__(self) -> None:
        self.events: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self.registered: list[tuple[int, str]] = []
        self.refreshed: list[tuple[int, str]] = []
        self.unregistered: list[tuple[int, str]] = []

    async def register(self, manager_id: int, connection_id: str):
        self.registered.append((manager_id, connection_id))
        return SimpleNamespace(events=self.events)

    async def refresh_presence(self, manager_id: int, connection_id: str) -> None:
        self.refreshed.append((manager_id, connection_id))

    async def unregister(self, manager_id: int, connection_id: str) -> None:
        self.unregistered.append((manager_id, connection_id))


async def test_stream_returns_ready_headers_keepalive_and_cleans_up(
    db_session,
    monkeypatch,
) -> None:
    manager = User(telegram_id=834001, role=int(UserRole.MANAGER))
    db_session.add(manager)
    await db_session.commit()
    hub = FakeRealtimeHub()
    db_trace: list[str] = []

    @asynccontextmanager
    async def fake_create_db_session():
        db_trace.append("open")
        try:
            yield db_session
        finally:
            db_trace.append("close")

    monkeypatch.setattr(manager_router, "create_db_session", fake_create_db_session)
    monkeypatch.setattr(manager_router, "manager_realtime_hub", hub)
    monkeypatch.setattr(settings, "manager_realtime_keepalive_seconds", 0.001)
    connection_id = str(uuid4())

    response = await manager_router.manager_realtime_stream(manager, connection_id)

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert db_trace == ["open", "close"]

    iterator = response.body_iterator
    ready = await anext(iterator)
    event_line, data_line = ready.strip().splitlines()
    assert event_line == "event: realtime.ready"
    assert json.loads(data_line.removeprefix("data: ")) == {
        "type": "realtime.ready",
        "payload": {"unreadTotal": 0},
        "managerId": manager.id,
    }
    assert await anext(iterator) == ": keepalive\n\n"
    assert hub.registered == [(manager.id, connection_id)]
    await asyncio.sleep(0.003)
    assert hub.refreshed
    assert set(hub.refreshed) == {(manager.id, connection_id)}

    await iterator.aclose()
    assert hub.unregistered == [(manager.id, connection_id)]


async def test_stream_refreshes_presence_while_events_keep_flowing(
    db_session,
    monkeypatch,
) -> None:
    """Presence TTL продлевается независимо от keepalive timeout очереди."""
    manager = User(telegram_id=834004, role=int(UserRole.MANAGER))
    db_session.add(manager)
    await db_session.commit()
    hub = FakeRealtimeHub()

    @asynccontextmanager
    async def fake_create_db_session():
        yield db_session

    monkeypatch.setattr(manager_router, "create_db_session", fake_create_db_session)
    monkeypatch.setattr(manager_router, "manager_realtime_hub", hub)
    monkeypatch.setattr(settings, "manager_realtime_keepalive_seconds", 0.001)
    connection_id = str(uuid4())
    response = await manager_router.manager_realtime_stream(manager, connection_id)
    iterator = response.body_iterator

    await anext(iterator)
    hub.events.put_nowait(
        {
            "type": "manager.refresh",
            "payload": {"reason": "chat.message.created"},
            "managerId": manager.id,
        }
    )
    assert "event: manager.refresh" in await anext(iterator)

    # Generator приостановлен на yield события, но отдельный heartbeat обязан
    # продолжать TTL presence/viewing без зависимости от timeout очереди.
    await asyncio.sleep(0.005)
    assert hub.refreshed

    refresh_count = len(hub.refreshed)
    await iterator.aclose()
    assert hub.unregistered == [(manager.id, connection_id)]
    await asyncio.sleep(0.003)
    assert len(hub.refreshed) == refresh_count


async def test_stream_rejects_missing_auth_and_non_manager(db_session, monkeypatch) -> None:
    from app.main import app

    customer = User(telegram_id=834002, role=int(UserRole.USER))
    db_session.add(customer)
    await db_session.commit()
    monkeypatch.setattr(settings, "jwt_secret", "manager-realtime-api-test-secret-32-bytes")

    @asynccontextmanager
    async def fake_create_db_session():
        yield db_session

    monkeypatch.setattr(deps, "create_db_session", fake_create_db_session)
    transport = ASGITransport(app=app)
    headers = {"X-Manager-Realtime-Connection-Id": str(uuid4())}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing_auth = await client.get("/api/manager/realtime/stream", headers=headers)
        user_token = create_access_token({"sub": str(customer.id), "role": customer.role})
        non_manager = await client.get(
            "/api/manager/realtime/stream",
            headers={**headers, "Authorization": f"Bearer {user_token}"},
        )

    assert missing_auth.status_code == 401
    assert non_manager.status_code == 403


async def test_stream_auth_accepts_manager_and_closes_session(db_session, monkeypatch) -> None:
    manager = User(telegram_id=834003, role=int(UserRole.MANAGER))
    db_session.add(manager)
    await db_session.commit()
    monkeypatch.setattr(settings, "jwt_secret", "manager-realtime-api-test-secret-32-bytes")
    session_trace: list[str] = []

    @asynccontextmanager
    async def fake_create_db_session():
        session_trace.append("open")
        try:
            yield db_session
        finally:
            session_trace.append("close")

    monkeypatch.setattr(deps, "create_db_session", fake_create_db_session)
    token = create_access_token({"sub": str(manager.id), "role": manager.role})

    authenticated = await deps.get_manager_stream_user(f"Bearer {token}")

    assert authenticated.id == manager.id
    assert session_trace == ["open", "close"]


def test_stream_does_not_retain_yield_dependency_during_response() -> None:
    """SSE не должен держать request-scoped DB session до disconnect клиента."""
    from app.main import app

    route = next(route for route in app.routes if route.path == "/api/manager/realtime/stream")
    pending = list(route.dependant.dependencies)
    retained_yield_dependencies: list[str] = []
    while pending:
        dependency = pending.pop()
        pending.extend(dependency.dependencies)
        if inspect.isasyncgenfunction(dependency.call) and dependency.scope != "function":
            retained_yield_dependencies.append(dependency.call.__name__)

    assert retained_yield_dependencies == []


async def test_legacy_manager_realtime_http_routes_are_not_served() -> None:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ticket = await client.post("/api/manager/realtime/ticket")
        websocket = await client.get("/api/manager/realtime/ws")

    assert ticket.status_code == 404
    assert websocket.status_code == 404
