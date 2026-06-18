from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.models.admin import Admin


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

    response = await client.get('/api/admin/list')

    assert response.status_code == 401
    assert response.json()['detail'] == 'Not authenticated'


@pytest.mark.asyncio
async def test_admin_can_list_existing_admins(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username='root', email='root@example.com', password_hash='unused')
    another_admin = Admin(username='ops', email='ops@example.com', password_hash='unused')
    db_session.add_all([admin, another_admin])
    await db_session.flush()
    token = create_access_token({'sub': str(admin.id), 'type': 'admin'})

    response = await client.get('/api/admin/list', headers={'Authorization': f'Bearer {token}'})

    assert response.status_code == 200
    assert response.json() == [
        {
            'id': admin.id,
            'username': 'root',
            'email': 'root@example.com',
            'createdAt': admin.createdAt.isoformat().replace('+00:00', 'Z'),
            'updatedAt': admin.updatedAt.isoformat().replace('+00:00', 'Z'),
        },
        {
            'id': another_admin.id,
            'username': 'ops',
            'email': 'ops@example.com',
            'createdAt': another_admin.createdAt.isoformat().replace('+00:00', 'Z'),
            'updatedAt': another_admin.updatedAt.isoformat().replace('+00:00', 'Z'),
        },
    ]


@pytest.mark.asyncio
async def test_admin_can_create_new_admin(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username='root', email='root@example.com', password_hash='unused')
    db_session.add(admin)
    await db_session.flush()
    token = create_access_token({'sub': str(admin.id), 'type': 'admin'})

    response = await client.post(
        '/api/admin/add',
        headers={'Authorization': f'Bearer {token}'},
        json={'username': 'alice', 'email': 'alice@example.com', 'password': 'Secret123'},
    )

    assert response.status_code == 201
    assert response.json()['username'] == 'alice'
    assert response.json()['email'] == 'alice@example.com'

    created = await db_session.scalar(select(Admin).where(Admin.username == 'alice'))
    assert created is not None
    assert created.email == 'alice@example.com'
    assert created.password_hash == hashlib.sha256(b'Secret123').hexdigest()


@pytest.mark.asyncio
async def test_admin_can_change_password_for_existing_admin(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username='root', email='root@example.com', password_hash='unused')
    target = Admin(
        username='alice',
        email='alice@example.com',
        password_hash=hashlib.sha256(b'OldPassword').hexdigest(),
    )
    db_session.add_all([admin, target])
    await db_session.flush()
    token = create_access_token({'sub': str(admin.id), 'type': 'admin'})

    response = await client.put(
        '/api/admin/password',
        headers={'Authorization': f'Bearer {token}'},
        json={'admin_id': target.id, 'password': 'NewPassword123'},
    )

    assert response.status_code == 200
    assert response.json() == {'ok': True}

    await db_session.refresh(target)
    assert target.password_hash == hashlib.sha256(b'NewPassword123').hexdigest()


@pytest.mark.asyncio
async def test_admin_can_delete_another_admin(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username='root', email='root@example.com', password_hash='unused')
    target = Admin(username='alice', email='alice@example.com', password_hash='unused')
    db_session.add_all([admin, target])
    await db_session.flush()
    token = create_access_token({'sub': str(admin.id), 'type': 'admin'})

    response = await client.delete(
        f'/api/admin/delete/{target.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert await db_session.get(Admin, target.id) is None


@pytest.mark.asyncio
async def test_delete_rejects_self_deletion(
    admin_crud_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = admin_crud_api_client
    admin = Admin(username='root', email='root@example.com', password_hash='unused')
    db_session.add(admin)
    await db_session.flush()
    token = create_access_token({'sub': str(admin.id), 'type': 'admin'})

    response = await client.delete(
        f'/api/admin/delete/{admin.id}',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'You cannot delete yourself'
