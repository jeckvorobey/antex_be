from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from app.api.routers import manager
from app.core.database import get_db_session
from app.core.security import create_access_token
from app.enums.user import UserRole


async def test_sse_releases_auth_session_before_first_event(monkeypatch) -> None:
    """Реальный ASGI lifecycle закрывает auth dependency до начала долгого ответа."""
    released = False

    async def auth_session():
        nonlocal released
        try:
            yield SimpleNamespace()
        finally:
            released = True

    @asynccontextmanager
    async def transient_session():
        yield SimpleNamespace()

    async def bounded_events(events):
        try:
            assert released, "SSE удерживает request-scoped auth session"
            yield await anext(events)
        finally:
            await events.aclose()

    def bounded_response(events, **kwargs):
        return StreamingResponse(bounded_events(events), **kwargs)

    monkeypatch.setattr(
        "app.api.deps.UserRepository.get_one",
        AsyncMock(return_value=SimpleNamespace(id=42, role=int(UserRole.MANAGER))),
    )
    monkeypatch.setattr(manager, "create_db_session", transient_session)
    monkeypatch.setattr(manager.ChatRepository, "unread_total", AsyncMock(return_value=3))
    monkeypatch.setattr(manager, "StreamingResponse", bounded_response)
    monkeypatch.setattr(manager.manager_realtime_hub, "register", AsyncMock())
    monkeypatch.setattr(manager.manager_realtime_hub, "unregister", AsyncMock())
    app = FastAPI()
    app.include_router(manager.router)
    app.dependency_overrides[get_db_session] = auth_session
    token = create_access_token({"sub": "42", "type": "user"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/manager/realtime/stream",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Manager-Realtime-Connection-Id": str(uuid4()),
            },
        )
    assert response.status_code == 200
    assert '"unreadTotal": 3' in response.text
    manager.manager_realtime_hub.register.assert_awaited_once()
    manager.manager_realtime_hub.unregister.assert_awaited_once()


async def test_sse_refreshes_presence_when_events_arrive_without_timeout(monkeypatch) -> None:
    """Поток частых событий не должен позволять presence истечь."""

    @asynccontextmanager
    async def transient_session():
        yield SimpleNamespace()

    queue = asyncio.Queue()
    await queue.put({"type": "chat.message.created", "payload": {}})
    monkeypatch.setattr(manager, "create_db_session", transient_session)
    monkeypatch.setattr(manager.ChatRepository, "unread_total", AsyncMock(return_value=0))
    monkeypatch.setattr(
        manager.manager_realtime_hub,
        "register",
        AsyncMock(return_value=SimpleNamespace(events=queue)),
    )
    refresh = AsyncMock()
    monkeypatch.setattr(manager.manager_realtime_hub, "refresh_presence", refresh)
    monkeypatch.setattr(manager.manager_realtime_hub, "unregister", AsyncMock())
    connection_id = str(uuid4())
    response = await manager.manager_realtime_stream(manager_id=42, connection_id=connection_id)
    events = response.body_iterator
    try:
        assert "realtime.ready" in await anext(events)
        assert "chat.message.created" in await anext(events)
        refresh.assert_awaited_with(42, connection_id)
    finally:
        await events.aclose()
