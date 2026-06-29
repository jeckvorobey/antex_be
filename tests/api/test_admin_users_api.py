from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.enums.user import UserRole
from app.models.admin import Admin
from app.models.user import User


@pytest.fixture
async def admin_users_api_client(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession]]:
    from app.main import app

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_update_user_role_to_manager(
    admin_users_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_users_api_client
    admin = Admin(username="admin", password_hash="unused")
    user = User(
        telegram_id=700001,
        username="johndoe",
        first_name="John",
        role=int(UserRole.USER),
        city_id=None,
    )
    db_session.add_all([admin, user])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.patch(
        f"/api/admin/users/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": int(UserRole.MANAGER)},
    )

    assert response.status_code == 200
    assert response.json()["role"] == int(UserRole.MANAGER)
    assert response.json()["city_id"] is None


@pytest.mark.asyncio
async def test_admin_cannot_assign_second_global_manager(
    admin_users_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_users_api_client
    admin = Admin(username="admin", password_hash="unused")
    user1 = User(
        telegram_id=800009, username="user1", first_name="Alice", role=int(UserRole.USER)
    )
    user2 = User(
        telegram_id=800010, username="user2", first_name="Bob", role=int(UserRole.USER)
    )
    db_session.add_all([admin, user1, user2])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.get(
        "/api/admin/users",
        params={"search": str(user1.id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == user1.id


@pytest.mark.asyncio
async def test_admin_list_users_search_no_results(
    admin_users_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_users_api_client
    admin = Admin(username="admin", password_hash="unused")
    user = User(
        telegram_id=800011, username="alice", first_name="Alice", role=int(UserRole.USER)
    )
    db_session.add_all([admin, user])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.get(
        "/api/admin/users",
        params={"search": "nonexistent"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0
