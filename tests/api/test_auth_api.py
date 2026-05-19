from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.enums.user import UserRole
from app.models.user import User


@pytest.fixture
async def auth_api_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession]]:
    from app.core.config import settings
    from app.main import app
    from app.services import auth as auth_service

    settings.jwt_secret = "test-secret-for-auth-api"
    monkeypatch.setattr(
        auth_service,
        "validate_telegram_init_data",
        lambda _: {
            "user": json.dumps(
                {
                    "id": 123456,
                    "first_name": "No",
                    "last_name": "Username",
                    "language_code": "ru",
                    "is_bot": False,
                    "is_premium": True,
                }
            )
        },
    )

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_auth_contact_returns_not_ready_without_username_or_phone(
    auth_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = auth_api_client
    user = User(
        telegram_id=700001,
        username=None,
        first_name="Contact",
        role=int(UserRole.USER),
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token({"sub": str(user.id), "role": user.role})
    response = await client.get(
        "/api/auth/contact",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ready": False,
        "contact": None,
        "source": None,
        "phone": None,
        "username": None,
    }


@pytest.mark.asyncio
async def test_auth_contact_persists_phone_for_future_order_submit(
    auth_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = auth_api_client

    auth_response = await client.post(
        "/api/auth/telegram",
        json={"init_data": "stub"},
    )
    assert auth_response.status_code == 200

    token = auth_response.json()["access_token"]
    save_response = await client.put(
        "/api/auth/contact",
        headers={"Authorization": f"Bearer {token}"},
        json={"phone": "+79991234567"},
    )

    assert save_response.status_code == 200
    assert save_response.json() == {
        "ready": True,
        "contact": "+79991234567",
        "source": "phone",
        "phone": "+79991234567",
        "username": None,
    }

    contact_response = await client.get(
        "/api/auth/contact",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert contact_response.status_code == 200
    assert contact_response.json()["contact"] == "+79991234567"
    assert contact_response.json()["ready"] is True

    stored_user = await db_session.get(User, 1)
    assert stored_user is not None
    assert stored_user.phone == "+79991234567"
