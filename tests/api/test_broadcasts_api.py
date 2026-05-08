from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.models.admin import Admin


@pytest.fixture
async def api_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession, AsyncMock]]:
    from app.api.routers import broadcasts
    from app.core.config import settings
    from app.main import app

    settings.jwt_secret = "test-secret-for-broadcasts-api"
    schedule_mock = AsyncMock()
    monkeypatch.setattr(broadcasts, "schedule_broadcast", schedule_mock)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session, schedule_mock

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_can_create_and_list_broadcasts(
    api_client: tuple[AsyncClient, AsyncSession, AsyncMock],
) -> None:
    client, db_session, schedule_mock = api_client
    admin = Admin(username="admin", password_hash="unused")
    db_session.add(admin)
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    create_response = await client.post(
        "/api/admin/broadcasts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": "Новости AntEx",
            "format": "plain",
            "speed_mode": "free",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["status"] == "pending"
    assert created["target_rps"] == 28
    schedule_mock.assert_awaited_once_with(broadcast_id=created["id"])

    list_response = await client.get(
        "/api/admin/broadcasts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert list_response.status_code == 200
    assert list_response.json()[0]["text"] == "Новости AntEx"
