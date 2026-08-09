from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
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

    settings.jwt_secret = "test-secret-for-auth-api-at-least-32-bytes"
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


@pytest.mark.asyncio
async def test_auth_contact_uses_dev_user_without_bearer_token(
    auth_api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = auth_api_client
    user = User(
        telegram_id=333366854,
        username=None,
        first_name="Dev",
        role=int(UserRole.USER),
    )
    db_session.add(user)
    await db_session.flush()

    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "dev_user_id", 333366854)

    save_response = await client.put(
        "/api/auth/contact",
        json={"phone": "+79991234567"},
    )

    assert save_response.status_code == 200
    assert save_response.json()["contact"] == "+79991234567"
    assert save_response.json()["ready"] is True

    contact_response = await client.get("/api/auth/contact")
    assert contact_response.status_code == 200
    assert contact_response.json()["phone"] == "+79991234567"

    users_count = await db_session.scalar(select(func.count(User.id)))
    assert users_count == 1


@pytest.mark.asyncio
async def test_telegram_auth_returns_new_user_without_write_access(
    auth_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Ловит потерю bootstrap-признаков для нового пользователя без разрешения."""
    client, db_session = auth_api_client

    response = await client.post("/api/auth/telegram", json={"init_data": "stub"})

    assert response.status_code == 200
    assert response.json()["is_new_user"] is True
    assert response.json()["telegram_write_access"] is False
    stored_user = await db_session.scalar(select(User).where(User.telegram_id == 123456))
    assert stored_user is not None
    assert stored_user.telegram_write_access is False


@pytest.mark.asyncio
async def test_telegram_auth_promotes_signed_allows_write_to_pm(
    auth_api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ловит игнорирование положительного allows_write_to_pm из validated initData."""
    client, db_session = auth_api_client
    from app.services import auth as auth_service

    monkeypatch.setattr(
        auth_service,
        "validate_telegram_init_data",
        lambda _: {
            "user": json.dumps(
                {
                    "id": 456789,
                    "first_name": "Allowed",
                    "is_bot": False,
                    "allows_write_to_pm": True,
                }
            )
        },
    )

    response = await client.post("/api/auth/telegram", json={"init_data": "signed"})

    assert response.status_code == 200
    assert response.json()["telegram_write_access"] is True
    stored_user = await db_session.scalar(select(User).where(User.telegram_id == 456789))
    assert stored_user is not None
    assert stored_user.telegram_write_access is True


@pytest.mark.asyncio
async def test_telegram_auth_missing_flag_does_not_revoke_cached_access(
    auth_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Ловит ошибочное понижение ранее подтверждённого разрешения при новом auth."""
    client, db_session = auth_api_client
    user = User(
        telegram_id=123456,
        first_name="Existing",
        role=int(UserRole.USER),
        telegram_write_access=True,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post("/api/auth/telegram", json={"init_data": "stub"})

    assert response.status_code == 200
    assert response.json()["is_new_user"] is False
    assert response.json()["telegram_write_access"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_access"),
    [("allowed", True), ("cancelled", False), ("unsupported", False)],
)
async def test_write_access_endpoint_persists_current_user_outcome(
    auth_api_client: tuple[AsyncClient, AsyncSession],
    status: str,
    expected_access: bool,
) -> None:
    """Ловит неверное сопоставление нативного результата при локальном состоянии."""
    client, db_session = auth_api_client
    user = User(
        telegram_id=800001,
        first_name="Gate",
        role=int(UserRole.USER),
        telegram_write_access=not expected_access,
    )
    db_session.add(user)
    await db_session.commit()
    token = create_access_token({"sub": str(user.id), "role": user.role})

    response = await client.post(
        "/api/users/me/telegram-write-access",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": status},
    )

    assert response.status_code == 200
    assert response.json() == {"telegram_write_access": expected_access}
    await db_session.refresh(user)
    assert user.telegram_write_access is expected_access


@pytest.mark.asyncio
async def test_write_access_endpoint_rejects_foreign_user_identifier(
    auth_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Ловит возможность подменить целевого пользователя через payload."""
    client, db_session = auth_api_client
    current = User(telegram_id=800002, first_name="Current", role=int(UserRole.USER))
    foreign = User(telegram_id=800003, first_name="Foreign", role=int(UserRole.USER))
    db_session.add_all([current, foreign])
    await db_session.commit()
    token = create_access_token({"sub": str(current.id), "role": current.role})

    response = await client.post(
        "/api/users/me/telegram-write-access",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "allowed", "user_id": foreign.id},
    )

    assert response.status_code == 422
    await db_session.refresh(foreign)
    assert foreign.telegram_write_access is False


@pytest.mark.asyncio
@pytest.mark.parametrize("token_type", ["admin", "admin_refresh"])
async def test_write_access_endpoint_rejects_admin_token_types(
    auth_api_client: tuple[AsyncClient, AsyncSession],
    token_type: str,
) -> None:
    """Блокирует административные токены при совпадающем идентификаторе."""
    client, db_session = auth_api_client
    user = User(telegram_id=800004, first_name="Collision", role=int(UserRole.USER))
    db_session.add(user)
    await db_session.commit()
    token = create_access_token({"sub": str(user.id), "type": token_type})

    response = await client.post(
        "/api/users/me/telegram-write-access",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "allowed"},
    )

    assert response.status_code == 403
    await db_session.refresh(user)
    assert user.telegram_write_access is False
