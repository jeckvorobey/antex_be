# ruff: noqa: RUF001
from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator

import pytest
from altcha import Challenge, Payload, solve_challenge
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.enums.user import UserRole
from app.models.admin import Admin
from app.models.user import User
from app.services.site_lead_captcha import create_site_lead_challenge
from app.services.site_lead_notifications import build_site_lead_manager_text


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.send_error: Exception | None = None

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.set_values: set[str] = set()

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def set(self, key: str, value: str, *, ex: int, nx: bool = False) -> bool:
        if nx and key in self.set_values:
            return False
        self.set_values.add(key)
        return True


def test_site_lead_telegram_text_escapes_html_controlled_fields() -> None:
    """Публичный ввод не должен становиться Telegram HTML-разметкой."""
    lead = type(
        "Lead",
        (),
        {
            "id": 1,
            "messenger": "<b>Telegram</b>",
            "contact": "<script>alert(1)</script>",
            "topic": "<i>Обмен</i>",
            "message": "<a href=\"https://attacker.example\">текст</a>",
            "source": "<u>landing</u>",
        },
    )()

    assert build_site_lead_manager_text(lead) == (
        "🆕 Заявка с сайта #1\n\n"
        "💬 Мессенджер: &lt;b&gt;Telegram&lt;/b&gt;\n"
        "👤 Контакт: &lt;script&gt;alert(1)&lt;/script&gt;\n"
        "📌 Тема: &lt;i&gt;Обмен&lt;/i&gt;\n"
        "📝 Сообщение: &lt;a href=&quot;https://attacker.example&quot;&gt;текст&lt;/a&gt;\n"
        "🌐 Источник: &lt;u&gt;landing&lt;/u&gt;"
    )

def _valid_altcha_payload() -> str:
    challenge = Challenge.from_dict(create_site_lead_challenge())
    solution = solve_challenge(challenge, timeout=5)
    assert solution is not None
    return Payload(challenge, solution).to_base64()


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
            "altcha": _valid_altcha_payload(),
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
async def test_public_site_lead_challenge_is_signed_and_expires(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, _ = site_leads_api_client

    response = await client.get("/public/site-leads/challenge")

    assert response.status_code == 200
    payload = response.json()
    assert payload["parameters"]["algorithm"] == "PBKDF2/SHA-256"
    assert payload["parameters"]["expiresAt"] > 0
    assert payload["signature"]


@pytest.mark.asyncio
async def test_public_site_lead_post_requires_altcha_payload(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, _ = site_leads_api_client

    response = await client.post(
        "/public/site-leads",
        json={"contact": "@client", "message": "Нужен обмен"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_public_site_lead_post_rejects_invalid_altcha_payload(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import redis as redis_module

    client, _ = site_leads_api_client
    monkeypatch.setattr(redis_module, "redis_client", _FakeRedis())

    response = await client.post(
        "/public/site-leads",
        json={"contact": "@client", "message": "Нужен обмен", "altcha": "invalid"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_public_site_lead_post_rejects_replayed_altcha_payload(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import redis as redis_module

    client, _ = site_leads_api_client
    monkeypatch.setattr(redis_module, "redis_client", _FakeRedis())
    altcha_payload = _valid_altcha_payload()
    payload = {"contact": "@client", "message": "Нужен обмен", "altcha": altcha_payload}

    first = await client.post("/public/site-leads", json=payload)
    second = await client.post("/public/site-leads", json=payload)

    assert first.status_code == 201
    assert second.status_code == 403


@pytest.mark.asyncio
async def test_public_site_lead_post_rejects_reencoded_altcha_replay(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import redis as redis_module

    client, _ = site_leads_api_client
    monkeypatch.setattr(redis_module, "redis_client", _FakeRedis())
    altcha_payload = _valid_altcha_payload()
    decoded = json.loads(base64.b64decode(altcha_payload))
    reencoded_payload = base64.b64encode(
        json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode()
    ).decode()

    first = await client.post(
        "/public/site-leads",
        json={"contact": "@client", "message": "Нужен обмен", "altcha": altcha_payload},
    )
    replay = await client.post(
        "/public/site-leads",
        json={"contact": "@other", "message": "Другой обмен", "altcha": reencoded_payload},
    )

    assert first.status_code == 201
    assert replay.status_code == 403


@pytest.mark.asyncio
async def test_public_site_lead_post_is_rate_limited_before_database_write(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import redis as redis_module

    client, _ = site_leads_api_client
    fake_redis = _FakeRedis()
    monkeypatch.setattr(redis_module, "redis_client", fake_redis)

    for index in range(3):
        response = await client.post(
            "/public/site-leads",
            json={
                "contact": "@client",
                "message": f"Нужен обмен {index}",
                "altcha": _valid_altcha_payload(),
            },
        )
        assert response.status_code == 201

    response = await client.post(
        "/public/site-leads",
        json={
            "contact": "@client",
            "message": "Нужен обмен 3",
            "altcha": _valid_altcha_payload(),
        },
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком много заявок"


@pytest.mark.asyncio
async def test_public_site_lead_post_deduplicates_exact_payload(
    site_leads_api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import redis as redis_module

    client, _ = site_leads_api_client
    monkeypatch.setattr(redis_module, "redis_client", _FakeRedis())
    first_payload = {
        "contact": "@client",
        "message": "Нужен обмен",
        "altcha": _valid_altcha_payload(),
    }
    second_payload = {**first_payload, "altcha": _valid_altcha_payload()}

    first = await client.post("/public/site-leads", json=first_payload)
    second = await client.post("/public/site-leads", json=second_payload)

    assert first.status_code == 201
    assert second.status_code == 409


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
            "altcha": _valid_altcha_payload(),
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
            "altcha": _valid_altcha_payload(),
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
                "altcha": _valid_altcha_payload(),
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
