from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

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
    user1 = User(telegram_id=800009, username="user1", first_name="Alice", role=int(UserRole.USER))
    user2 = User(telegram_id=800010, username="user2", first_name="Bob", role=int(UserRole.USER))
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
    user = User(telegram_id=800011, username="alice", first_name="Alice", role=int(UserRole.USER))
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


@pytest.mark.asyncio
async def test_admin_list_users_includes_referral_and_aex_columns(
    admin_users_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_users_api_client
    admin = Admin(username="admin", password_hash="unused")
    user = User(
        telegram_id=800012,
        username="ref_admin_row",
        first_name="Referral",
        role=int(UserRole.USER),
        referral_code="REFROW12",
    )
    db_session.add_all([admin, user])
    await db_session.flush()
    await db_session.refresh(admin)
    await db_session.refresh(user)

    from app.services.aex import AexService
    from app.services.aex_rate import AexRateService

    await AexService().credit(db_session, user.id, Decimal("12.5"))
    await AexRateService().set_personal_rate(db_session, user.id, Decimal("0.015"))
    await db_session.commit()

    token = create_access_token({"sub": str(admin.id), "type": "admin"})
    response = await client.get(
        "/api/admin/users",
        params={"search": "ref_admin_row"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    row = data[0]
    assert row["referral_code"] == "REFROW12"
    assert row["referral_rate"] == "0.015000"
    assert row["referral_rate_percent"] == "1.500000"
    assert row["aex_balance"] == "12.50000000"


@pytest.mark.asyncio
async def test_admin_get_user_without_wallet_returns_referral_defaults(
    admin_users_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_users_api_client
    admin = Admin(username="admin", password_hash="unused")
    user = User(
        telegram_id=800013,
        username="ref_admin_detail",
        first_name="Referral",
        role=int(UserRole.USER),
        referral_code=None,
    )
    db_session.add_all([admin, user])
    await db_session.flush()
    await db_session.refresh(admin)
    await db_session.refresh(user)

    token = create_access_token({"sub": str(admin.id), "type": "admin"})
    response = await client.get(
        f"/api/admin/users/{user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    row = response.json()
    assert row["referral_code"] is None
    assert row["referral_rate"] == "0.002000"
    assert row["referral_rate_percent"] == "0.200000"
    assert row["aex_balance"] == "0"


@pytest.mark.asyncio
async def test_admin_generate_referral_code_for_single_user(
    admin_users_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_users_api_client
    admin = Admin(username="admin", password_hash="unused")
    target = User(telegram_id=800014, username="ref_single_target")
    other = User(telegram_id=800015, username="ref_single_other")
    db_session.add_all([admin, target, other])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.post(
        f"/api/admin/users/{target.id}/generate-referral-code",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert len(response.json()["referral_code"]) == 8
    await db_session.refresh(target)
    await db_session.refresh(other)
    assert target.referral_code == response.json()["referral_code"]
    assert other.referral_code is None


@pytest.mark.asyncio
async def test_admin_regenerate_referral_code_for_single_user_only(
    admin_users_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_users_api_client
    admin = Admin(username="admin", password_hash="unused")
    target = User(telegram_id=800016, username="ref_regen_target", referral_code="tH6wQ8Er")
    other = User(telegram_id=800017, username="ref_regen_other", referral_code="Y9mNc2Lp")
    db_session.add_all([admin, target, other])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.post(
        f"/api/admin/users/{target.id}/generate-referral-code",
        params={"regenerate": True},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    await db_session.refresh(target)
    await db_session.refresh(other)
    assert target.referral_code == response.json()["referral_code"]
    assert target.referral_code != "tH6wQ8Er"
    assert other.referral_code == "Y9mNc2Lp"
