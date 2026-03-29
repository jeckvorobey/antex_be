"""Тесты miniapp API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models.allowance import Allowance
from app.models.bank import Bank
from app.models.order import Order
from app.models.user import User


@pytest.fixture
async def seeded_user(db_session):
    user = User(
        id=777000,
        username="sergdev",
        first_name="Sergei",
        last_name="V",
        language_code="ru",
        is_bot=False,
        role=1,
        is_premium=True,
    )
    bank = Bank(code="SCB", name="Siam Commercial Bank")
    allowance = Allowance(value=0.02)

    db_session.add_all([user, bank, allowance])
    await db_session.flush()

    order = Order(
        UserId=user.id,
        BankId=bank.id,
        currencySell="RUB",
        amountSell=5000,
        currencyBuy="THB",
        amountBuy=1850,
        rate=2.7,
        status=1,
        methodGet="cash",
        contactTelegram="@sergdev",
        createdAt=datetime(2026, 3, 28, 9, 30, tzinfo=UTC),
        updatedAt=datetime(2026, 3, 28, 9, 30, tzinfo=UTC),
    )
    db_session.add(order)
    await db_session.flush()

    return {"user": user, "bank": bank, "order": order}


@pytest.fixture
async def seeded_user_without_order(db_session):
    user_id = 800000 + (uuid4().int % 100000)
    user = User(
        id=user_id,
        username=f"newuser_{user_id}",
        first_name="New",
        last_name="User",
        language_code="ru",
        is_bot=False,
        role=1,
        is_premium=False,
    )
    bank = Bank(code=f"KBANK-{uuid4().hex[:6]}", name="Kasikorn Bank")
    allowance = Allowance(value=0.02)

    db_session.add_all([user, bank, allowance])
    await db_session.flush()

    return {"user": user, "bank": bank}


@pytest.fixture
def auth_headers(monkeypatch, seeded_user):
    monkeypatch.setattr(settings, "jwt_secret", "miniapp-test-secret-0123456789abcdef")
    token = create_access_token({"sub": str(seeded_user["user"].id), "role": 1})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_without_order(monkeypatch, seeded_user_without_order):
    monkeypatch.setattr(settings, "jwt_secret", "miniapp-test-secret-0123456789abcdef")
    token = create_access_token({"sub": str(seeded_user_without_order["user"].id), "role": 1})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_home_returns_hybrid_content(client, auth_headers, monkeypatch):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 90.5,
            "USDTTHB": 33.4,
            "RUBTHB": 2.71,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.get("/api/miniapp/home", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["displayName"] == "Sergei V"
    assert payload["rates"]["featured"][0]["fromCurrency"] == "RUB"
    assert payload["services"][0]["id"] == "verification"
    assert payload["quickActions"][0]["title"] == "На рабочий стол"
    assert payload["services"][0]["icon"].startswith("mdi-")
    assert payload["quickActions"][0]["icon"].startswith("mdi-")
    assert payload["locations"][0]["city"] == "Bang Tao"


@pytest.mark.asyncio
async def test_home_allows_guest_access_without_auth(client, monkeypatch):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 90.5,
            "USDTTHB": 33.4,
            "RUBTHB": 2.71,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.get("/api/miniapp/home")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["displayName"] == "Sergei V"
    assert payload["profile"]["username"] == "sergeywebdev"


@pytest.mark.asyncio
async def test_exchange_screen_returns_pairs_and_quote_defaults(client, auth_headers, monkeypatch):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 91.0,
            "USDTTHB": 33.0,
            "RUBTHB": 2.75,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.get("/api/miniapp/exchange", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["calculator"]["fromCurrency"] == "RUB"
    assert payload["pairs"][0]["label"] == "RUB -> THB"
    assert payload["quote"]["amountBuy"] == 13750


@pytest.mark.asyncio
async def test_quote_recalculates_on_server(client, auth_headers, monkeypatch):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 90.0,
            "USDTTHB": 30.0,
            "RUBTHB": 3.0,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.get(
        "/api/miniapp/exchange/quote",
        params={"currencySell": "RUB", "currencyBuy": "THB", "amountSell": 6000},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["amountBuy"] == 18000
    assert payload["rate"] == 3.0
    assert payload["availableMethods"] == ["cash", "qr", "rs"]


@pytest.mark.asyncio
async def test_quote_preserves_fractional_amount_for_rub_to_usdt(client, auth_headers, monkeypatch):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 90.0,
            "USDTTHB": 30.0,
            "RUBTHB": 3.0,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.get(
        "/api/miniapp/exchange/quote",
        params={"currencySell": "RUB", "currencyBuy": "USDT", "amountSell": 5000},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["amountBuy"] == 55.56


@pytest.mark.asyncio
async def test_list_orders_returns_current_user_orders(client, auth_headers):
    response = await client.get("/api/miniapp/orders", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["contactTelegram"] == "@sergdev"


@pytest.mark.asyncio
async def test_profile_allows_guest_access_without_auth(client):
    response = await client.get("/api/miniapp/profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["displayName"] == "Sergei V"
    assert payload["menu"][0]["title"] == "Мои заявки"


@pytest.mark.asyncio
async def test_create_order_uses_server_side_quote_and_contact(
    client,
    auth_headers_without_order,
    seeded_user_without_order,
    monkeypatch,
):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 90.0,
            "USDTTHB": 30.0,
            "RUBTHB": 3.0,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.post(
        "/api/miniapp/orders",
        headers=auth_headers_without_order,
        json={
            "currencySell": "RUB",
            "currencyBuy": "THB",
            "amountSell": 7000,
            "contactTelegram": "@new-contact",
            "methodGet": "cash",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["amountBuy"] == 21000
    assert payload["contactTelegram"] == "@new-contact"
    assert payload["bank"]["code"] == seeded_user_without_order["bank"].code


@pytest.mark.asyncio
async def test_create_order_allows_guest_without_auth(client, monkeypatch):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 90.0,
            "USDTTHB": 30.0,
            "RUBTHB": 3.0,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.post(
        "/api/miniapp/orders",
        json={
            "currencySell": "RUB",
            "currencyBuy": "THB",
            "amountSell": 7000,
            "contactTelegram": "@guest-contact",
            "methodGet": "cash",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["amountBuy"] == 21000
    assert payload["contactTelegram"] == "@guest-contact"


@pytest.mark.asyncio
async def test_create_order_preserves_fractional_amount_for_rub_to_usdt(
    client,
    auth_headers_without_order,
    monkeypatch,
):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 90.0,
            "USDTTHB": 30.0,
            "RUBTHB": 3.0,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.post(
        "/api/miniapp/orders",
        headers=auth_headers_without_order,
        json={
            "currencySell": "RUB",
            "currencyBuy": "USDT",
            "amountSell": 5000,
            "contactTelegram": "@new-contact",
            "methodGet": "cash",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["amountBuy"] == 55.56


@pytest.mark.asyncio
async def test_create_order_normalizes_currency_codes(client, auth_headers_without_order, monkeypatch):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 90.0,
            "USDTTHB": 30.0,
            "RUBTHB": 3.0,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.post(
        "/api/miniapp/orders",
        headers=auth_headers_without_order,
        json={
            "currencySell": "rub",
            "currencyBuy": "usdt",
            "amountSell": 5000,
            "contactTelegram": "@new-contact",
            "methodGet": "cash",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["currencySell"] == "RUB"
    assert payload["currencyBuy"] == "USDT"


@pytest.mark.asyncio
async def test_create_order_defaults_method_get_to_cash_when_null(
    client,
    auth_headers_without_order,
    monkeypatch,
):
    async def fake_rates(_allowance: float | None = None) -> dict[str, float]:
        return {
            "USDTRUB": 90.0,
            "USDTTHB": 30.0,
            "RUBTHB": 3.0,
            "allowance": 0.02,
        }

    monkeypatch.setattr("app.api.routers.miniapp.get_exchange_rates", fake_rates)

    response = await client.post(
        "/api/miniapp/orders",
        headers=auth_headers_without_order,
        json={
            "currencySell": "RUB",
            "currencyBuy": "THB",
            "amountSell": 5000,
            "contactTelegram": "@new-contact",
            "methodGet": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["methodGet"] == "cash"


@pytest.mark.asyncio
async def test_profile_returns_user_summary_and_menu(client, auth_headers):
    response = await client.get("/api/miniapp/profile", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["username"] == "sergdev"
    assert payload["menu"][0]["id"] == "orders"
    assert payload["menu"][0]["icon"].startswith("mdi-")
