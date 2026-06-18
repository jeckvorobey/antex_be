from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.user import UserRole
from app.models.admin import Admin
from app.models.city import City
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
async def test_admin_can_promote_user_to_manager_without_city(
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
    city = City(name="Bangkok", country=Country.THAILAND)
    existing_manager = User(
        telegram_id=700001,
        username="manager",
        first_name="Manager",
        role=int(UserRole.MANAGER),
        city_id=None,
    )
    another_user = User(
        telegram_id=700002,
        username="johndoe",
        first_name="John",
        role=int(UserRole.USER),
    )
    db_session.add_all([admin, city, existing_manager, another_user])
    await db_session.flush()
    another_user.city_id = city.id
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.patch(
        f"/api/admin/users/{another_user.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": int(UserRole.MANAGER)},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Manager is already assigned"


@pytest.mark.asyncio
async def test_admin_cannot_assign_removed_admin_role(
    admin_users_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_users_api_client
    admin = Admin(username="admin", password_hash="unused")
    user = User(
        telegram_id=700003,
        username="legacyadmin",
        first_name="Legacy",
        role=int(UserRole.USER),
    )
    db_session.add_all([admin, user])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.patch(
        f"/api/admin/users/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": 1},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Value error, Only user and manager roles are allowed"
