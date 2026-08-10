from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.models.admin import Admin
from app.modules.broadcasts.models import Broadcast


async def create_admin_with_token(db_session: AsyncSession) -> str:
    admin = Admin(username="admin", password_hash="unused")
    db_session.add(admin)
    await db_session.flush()
    return create_access_token({"sub": str(admin.id), "type": "admin"})


async def create_broadcast_row(
    db_session: AsyncSession,
    *,
    admin_id: int,
    status: str = "pending",
) -> Broadcast:
    broadcast = Broadcast(
        status=status,
        audience_type="all_non_bot_users",
        text="Новости AntEx",
        format="html",
        button_text=None,
        button_url=None,
        speed_mode_requested="free",
        speed_mode_effective="free",
        target_rps=28,
        worker_count=8,
        total_count=3,
        success_count=1,
        failed_count=0,
        created_by_admin_id=admin_id,
        started_at=None,
        finished_at=None,
        last_error=None,
    )
    db_session.add(broadcast)
    await db_session.commit()
    await db_session.refresh(broadcast)
    return broadcast


@pytest.fixture
async def api_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession, AsyncMock]]:
    from app.api.routers import broadcasts
    from app.core.config import settings
    from app.main import app

    settings.jwt_secret = "test-secret-for-broadcasts-api-at-least-32-bytes"
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
    token = await create_admin_with_token(db_session)

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
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["text"] == "Новости AntEx"


@pytest.mark.asyncio
async def test_admin_can_stop_active_broadcast(
    api_client: tuple[AsyncClient, AsyncSession, AsyncMock],
) -> None:
    client, db_session, _ = api_client
    token = await create_admin_with_token(db_session)
    admin = await db_session.get(Admin, 1)
    assert admin is not None
    broadcast = await create_broadcast_row(db_session, admin_id=admin.id, status="running")

    response = await client.post(
        f"/api/admin/broadcasts/{broadcast.id}/stop",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"
    assert data["finished_at"] is not None
    assert data["last_error"] == "Остановлена администратором"
    assert data["success_count"] == 1
    assert data["failed_count"] == 0


@pytest.mark.asyncio
async def test_admin_can_create_new_broadcast_after_stopping_active_one(
    api_client: tuple[AsyncClient, AsyncSession, AsyncMock],
) -> None:
    client, db_session, schedule_mock = api_client
    token = await create_admin_with_token(db_session)
    admin = await db_session.get(Admin, 1)
    assert admin is not None
    active = await create_broadcast_row(db_session, admin_id=admin.id, status="running")

    stop_response = await client.post(
        f"/api/admin/broadcasts/{active.id}/stop",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert stop_response.status_code == 200

    create_response = await client.post(
        "/api/admin/broadcasts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": "Следующая рассылка",
            "format": "plain",
            "speed_mode": "free",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["status"] == "pending"
    schedule_mock.assert_awaited_once_with(broadcast_id=create_response.json()["id"])


@pytest.mark.asyncio
async def test_stop_missing_broadcast_returns_404(
    api_client: tuple[AsyncClient, AsyncSession, AsyncMock],
) -> None:
    client, db_session, _ = api_client
    token = await create_admin_with_token(db_session)

    response = await client.post(
        "/api/admin/broadcasts/999/stop",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
