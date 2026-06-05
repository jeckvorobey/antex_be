from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.models.admin import Admin


@pytest.fixture
async def site_leads_api_client(
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
async def test_public_site_lead_post_saves_landing_payload(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, _ = site_leads_api_client

    response = await client.post(
        "/public/site-leads",
        json={
            "messenger": "Max",
            "contact": "@client",
            "topic": "Обмен",
            "message": "Нужен обмен RUB на USDT",
            "source": "antex-landing",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == 1
    assert payload["messenger"] == "Max"
    assert payload["contact"] == "@client"
    assert payload["topic"] == "Обмен"
    assert payload["message"] == "Нужен обмен RUB на USDT"
    assert payload["source"] == "antex-landing"
    assert payload["createdAt"] is not None


@pytest.mark.asyncio
async def test_public_site_lead_post_requires_contact_and_message(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, _ = site_leads_api_client

    response = await client.post(
        "/public/site-leads",
        json={
            "messenger": "Telegram",
            "contact": "",
            "topic": "Обмен",
            "message": "",
            "source": "antex-landing",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_can_list_site_leads(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = site_leads_api_client
    admin = Admin(username="admin", password_hash="unused")
    db_session.add(admin)
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    await client.post(
        "/public/site-leads",
        json={
            "messenger": "Telegram",
            "contact": "+66990000000",
            "topic": "Наличные",
            "message": "Нужна выдача наличных",
            "source": "tets.antex.pro",
        },
    )

    response = await client.get(
        "/api/admin/site-leads",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["contact"] == "+66990000000"
    assert payload[0]["source"] == "tets.antex.pro"
