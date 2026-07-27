# ruff: noqa: RUF001
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.enums.user import UserRole
from app.models.admin import Admin
from app.models.user import User


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.send_error: Exception | None = None

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})


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
    assert payload["items"][0]["contact"] == "+66990000000"
    assert payload["items"][0]["source"] == "tets.antex.pro"


@pytest.mark.asyncio
async def test_public_site_lead_post_notifies_manager_after_save(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.telegram import bot as telegram_bot

    client, db_session = site_leads_api_client
    manager = User(
        telegram_id=700001,
        username="manager",
        first_name="Manager",
        role=int(UserRole.MANAGER),
    )
    db_session.add(manager)
    await db_session.flush()
    bot = _FakeBot()
    monkeypatch.setattr(telegram_bot, "bot", bot)

    response = await client.post(
        "/public/site-leads",
        json={
            "messenger": "Telegram",
            "contact": "@client",
            "topic": "Обмен",
            "message": "Нужен обмен RUB на USDT",
            "source": "tets.antex.pro",
        },
    )

    assert response.status_code == 201
    assert bot.sent == [
        {
            "chat_id": 700001,
            "text": "\n".join(
                [
                    "🆕 Заявка с сайта #1",
                    "",
                    "💬 Мессенджер: Telegram",
                    "👤 Контакт: @client",
                    "📌 Тема: Обмен",
                    "📝 Сообщение: Нужен обмен RUB на USDT",
                    "🌐 Источник: tets.antex.pro",
                ]
            ),
            "reply_markup": None,
        }
    ]


@pytest.mark.asyncio
async def test_public_site_lead_post_keeps_saved_lead_when_manager_notification_fails(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.telegram import bot as telegram_bot

    client, db_session = site_leads_api_client
    admin = Admin(username="admin", password_hash="unused")
    manager = User(
        telegram_id=700001,
        username="manager",
        first_name="Manager",
        role=int(UserRole.MANAGER),
    )
    db_session.add_all([admin, manager])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})
    bot = _FakeBot()
    bot.send_error = RuntimeError("telegram unavailable")
    monkeypatch.setattr(telegram_bot, "bot", bot)

    with caplog.at_level(logging.ERROR, logger="app.services.site_leads"):
        response = await client.post(
            "/public/site-leads",
            json={
                "messenger": "Telegram",
                "contact": "@client",
                "topic": "Обмен",
                "message": "Нужен обмен RUB на USDT",
                "source": "tets.antex.pro",
            },
        )

    assert response.status_code == 201
    list_response = await client.get(
        "/api/admin/site-leads",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["contact"] == "@client"
    assert "Failed to send site lead notification" in caplog.text
