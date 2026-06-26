from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.order import OrderStatus
from app.models.admin import Admin
from app.models.city import City
from app.models.order import Order
from app.models.user import User


@contextmanager
def count_sql_statements(db_session: AsyncSession) -> Iterator[list[str]]:
    statements: list[str] = []
    bind = db_session.get_bind()

    def before_cursor_execute(
        conn,
        cursor,
        statement: str,
        parameters,
        context,
        executemany: bool,
    ) -> None:
        del conn, cursor, parameters, context, executemany
        statements.append(statement)

    event.listen(bind, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(bind, "before_cursor_execute", before_cursor_execute)


@pytest.fixture
async def admin_crud_api_client(
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
async def test_admin_list_requires_authentication(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, _ = admin_crud_api_client

    response = await client.get("/api/admin/list")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_admin_can_list_existing_admins(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username="root", email="root@example.com", password_hash="unused")
    another_admin = Admin(username="ops", email="ops@example.com", password_hash="unused")
    db_session.add_all([admin, another_admin])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.get("/api/admin/list", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": admin.id,
            "username": "root",
            "email": "root@example.com",
            "createdAt": admin.createdAt.isoformat().replace("+00:00", "Z"),
            "updatedAt": admin.updatedAt.isoformat().replace("+00:00", "Z"),
        },
        {
            "id": another_admin.id,
            "username": "ops",
            "email": "ops@example.com",
            "createdAt": another_admin.createdAt.isoformat().replace("+00:00", "Z"),
            "updatedAt": another_admin.updatedAt.isoformat().replace("+00:00", "Z"),
        },
    ]


@pytest.mark.asyncio
async def test_admin_can_create_new_admin(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username="root", email="root@example.com", password_hash="unused")
    db_session.add(admin)
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.post(
        "/api/admin/add",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "alice", "email": "alice@example.com", "password": "Secret123"},
    )

    assert response.status_code == 201
    assert response.json()["username"] == "alice"
    assert response.json()["email"] == "alice@example.com"

    created = await db_session.scalar(select(Admin).where(Admin.username == "alice"))
    assert created is not None
    assert created.email == "alice@example.com"
    assert created.password_hash == hashlib.sha256(b"Secret123").hexdigest()


@pytest.mark.asyncio
async def test_admin_can_change_password_for_existing_admin(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username="root", email="root@example.com", password_hash="unused")
    target = Admin(
        username="alice",
        email="alice@example.com",
        password_hash=hashlib.sha256(b"OldPassword").hexdigest(),
    )
    db_session.add_all([admin, target])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.put(
        "/api/admin/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"admin_id": target.id, "password": "NewPassword123"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    await db_session.refresh(target)
    assert target.password_hash == hashlib.sha256(b"NewPassword123").hexdigest()


@pytest.mark.asyncio
async def test_admin_can_delete_another_admin(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username="root", email="root@example.com", password_hash="unused")
    target = Admin(username="alice", email="alice@example.com", password_hash="unused")
    db_session.add_all([admin, target])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.delete(
        f"/api/admin/delete/{target.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert await db_session.get(Admin, target.id) is None


@pytest.mark.asyncio
async def test_delete_rejects_self_deletion(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username="root", email="root@example.com", password_hash="unused")
    db_session.add(admin)
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.delete(
        f"/api/admin/delete/{admin.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "You cannot delete yourself"


@pytest.mark.asyncio
async def test_admin_orders_list_loads_related_data_in_bulk(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username="root", email="root@example.com", password_hash="unused")
    city = City(name="Bangkok", country=Country.THAILAND)
    customer = User(telegram_id=900001, username="customer", first_name="Customer")
    db_session.add_all([admin, city, customer])
    await db_session.flush()
    orders = [
        Order(
            UserId=customer.id,
            CityId=city.id,
            country=Country.THAILAND,
            currencySell="RUB",
            amountSell=5000 + index,
            currencyBuy="THB",
            amountBuy=2000 + index,
            rate=0.4,
            status=int(OrderStatus.CREATED),
            methodGet="cash",
            publicNumber=f"202606{index:04d}",
            createdAt=datetime(2026, 6, index, 12, 0, tzinfo=UTC),
        )
        for index in range(1, 5)
    ]
    db_session.add_all(orders)
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    with count_sql_statements(db_session) as statements:
        response = await client.get(
            "/api/admin/orders",
            params={"limit": 2, "offset": 1},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert [item["publicNumber"] for item in payload["items"]] == [
        "2026060003",
        "2026060002",
    ]
    select_count = sum(
        1 for statement in statements if statement.lstrip().upper().startswith("SELECT")
    )
    assert select_count <= 5
