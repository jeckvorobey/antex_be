from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.routers.admin import get_today_start_for_timezone
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.order import OrderStatus
from app.enums.user import UserRole
from app.models.admin import Admin
from app.models.city import City
from app.models.order import Order
from app.models.rate import Rate
from app.models.user import User


@pytest.fixture
async def api_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession]]:
    from app.core.config import settings
    from app.main import app
    from app.services import order_flow

    settings.jwt_secret = "test-secret-for-miniapp-contract"
    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session

    app.dependency_overrides.clear()


async def seed_exchange_data(db_session: AsyncSession) -> tuple[City, User, User]:
    city = City(name="Bangkok", country=Country.THAILAND)
    manager = User(
        telegram_id=700001,
        username="manager",
        first_name="Order",
        role=int(UserRole.MANAGER),
    )
    customer = User(
        telegram_id=700002,
        username="customer",
        first_name="Happy",
        role=int(UserRole.USER),
    )
    db_session.add_all(
        [
            city,
            manager,
            customer,
            Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND),
            Rate(currency="RUBGEL", price=0.03, margin=3.0, country=Country.GEORGIA),
            Rate(currency="RUBVND", price=280.0, margin=3.0, country=Country.VIETNAM),
            Rate(currency="USDTTHB", price=36.2, margin=3.0, country=Country.THAILAND),
            Rate(currency="USDTGEL", price=2.7, margin=3.0, country=Country.GEORGIA),
            Rate(currency="USDTVND", price=25500.0, margin=3.0, country=Country.VIETNAM),
        ]
    )
    await db_session.flush()

    manager.city_id = city.id
    customer.city_id = city.id
    await db_session.flush()
    return city, manager, customer


@pytest.mark.asyncio
async def test_miniapp_home_and_exchange_are_backend_driven(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    home_response = await client.get(
        "/api/miniapp/home",
        headers={"Authorization": f"Bearer {token}"},
    )
    exchange_response = await client.get(
        "/api/miniapp/exchange",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert home_response.status_code == 200
    home = home_response.json()
    assert home["profile"]["displayName"] == "Happy"
    assert home["rates"]["previewLimit"] == 3
    assert [pair["id"] for pair in home["rates"]["featured"]] == [
        "rub-thb",
        "usdt-thb",
        "rub-vnd",
        "usdt-vnd",
        "rub-gel",
        "usdt-gel",
    ]
    assert home["rates"]["chips"] == ["USDT", "THB", "RUB", "GEL", "VND"]
    assert [country["label"] for country in home["countries"]] == [
        "Таиланд",
        "Вьетнам",
        "Грузия",
    ]
    assert home["countries"][0]["currency"] == "THB"
    assert home["locations"][0]["country"] == "thailand"
    assert home["locations"][0]["countryLabel"] == "Таиланд"
    assert home["locations"][0]["id"] == str(city.id)
    assert home["rates"]["featured"][0]["country"] == "thailand"
    assert home["rates"]["featured"][0]["fromCurrency"] == "RUB"
    assert home["rates"]["featured"][0]["toCurrency"] == "THB"
    assert home["rates"]["featured"][0]["amountSellExample"] == 5000
    assert home["rates"]["featured"][0]["availableMethods"] == ["qrcode", "cash"]
    assert home["rates"]["featured"][1]["availableMethods"] == ["qrcode", "cash"]

    assert exchange_response.status_code == 200
    exchange = exchange_response.json()
    assert exchange["calculator"] == {
        "fromCurrency": "RUB",
        "toCurrency": "THB",
        "amountSell": 5000,
    }
    assert exchange["quote"]["rate"] == 0.4
    assert exchange["quote"]["rateDisplay"] == "0.40"
    assert exchange["quote"]["rateText"] == "1 RUB = 0.40 THB"
    assert exchange["quote"]["amountBuy"] == pytest.approx(5000 * 0.4)
    assert exchange["pairs"][0]["id"] == "rub-thb"
    assert exchange["pairs"][0]["fromCurrency"] == "RUB"
    assert exchange["pairs"][0]["toCurrency"] == "THB"
    assert exchange["pairs"][0]["rate"] == pytest.approx(0.4)
    assert exchange["pairs"][0]["rateDisplay"] == "0.40"
    assert exchange["pairs"][0]["rateText"] == "1 RUB = 0.40 THB"
    assert {"rub-gel", "rub-vnd", "usdt-gel", "usdt-vnd"} <= {
        pair["id"] for pair in exchange["pairs"]
    }


@pytest.mark.asyncio
async def test_miniapp_quote_rejects_reverse_pairs_outside_preliminary_contract(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    direct_response = await client.get(
        "/api/miniapp/exchange/quote",
        params={"currencySell": "RUB", "currencyBuy": "THB", "amountSell": 10000},
        headers={"Authorization": f"Bearer {token}"},
    )
    reverse_response = await client.get(
        "/api/miniapp/exchange/quote",
        params={"currencySell": "THB", "currencyBuy": "RUB", "amountSell": 410},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert direct_response.status_code == 200
    assert direct_response.json()["rate"] == 0.4
    assert direct_response.json()["rateDisplay"] == "0.40"
    assert direct_response.json()["rateText"] == "1 RUB = 0.40 THB"
    assert direct_response.json()["amountBuy"] == pytest.approx(10000 * 0.4)

    assert reverse_response.status_code == 422
    assert reverse_response.json()["code"] == "UNSUPPORTED_PAIR"


@pytest.mark.asyncio
async def test_miniapp_quote_supports_gel_and_vnd_pairs(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    rub_gel_response = await client.get(
        "/api/miniapp/exchange/quote",
        params={"currencySell": "RUB", "currencyBuy": "GEL", "amountSell": 10000},
        headers={"Authorization": f"Bearer {token}"},
    )
    usdt_vnd_response = await client.get(
        "/api/miniapp/exchange/quote",
        params={"currencySell": "USDT", "currencyBuy": "VND", "amountSell": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    reverse_response = await client.get(
        "/api/miniapp/exchange/quote",
        params={"currencySell": "GEL", "currencyBuy": "RUB", "amountSell": 30},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert rub_gel_response.status_code == 200
    assert rub_gel_response.json()["rate"] == 0.03
    assert rub_gel_response.json()["rateDisplay"] == "0.03"
    assert rub_gel_response.json()["rateText"] == "1 RUB = 0.03 GEL"
    assert rub_gel_response.json()["amountBuy"] == pytest.approx(10000 * 0.03)
    assert rub_gel_response.json()["availableMethods"] == ["qrcode", "cash"]

    assert usdt_vnd_response.status_code == 200
    assert usdt_vnd_response.json()["rate"] == 24735.0
    assert usdt_vnd_response.json()["rateDisplay"] == "24735.00"
    assert usdt_vnd_response.json()["rateText"] == "1 USDT = 24735.00 VND"
    assert usdt_vnd_response.json()["amountBuy"] == pytest.approx(2 * 24735.0)
    assert usdt_vnd_response.json()["availableMethods"] == ["qrcode", "cash"]

    assert reverse_response.status_code == 422
    assert reverse_response.json()["code"] == "UNSUPPORTED_PAIR"


@pytest.mark.asyncio
async def test_miniapp_quote_rejects_pairs_outside_canonical_contract(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.get(
        "/api/miniapp/exchange/quote",
        params={"currencySell": "THB", "currencyBuy": "USDT", "amountSell": 1000},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_PAIR"


@pytest.mark.asyncio
async def test_miniapp_order_is_created_with_preliminary_client_quote(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "rub",
            "amountSell": 10000,
            "currencyBuy": "thb",
            "amountBuy": 123.45,
            "rate": 9.99,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 201
    order = response.json()
    assert order["cityId"] is None
    assert order["country"] == "thailand"
    assert order["currencySell"] == "RUB"
    assert order["currencyBuy"] == "THB"
    assert order["rate"] == 9.99
    assert order["amountBuy"] == pytest.approx(123.45)
    assert order["contactTelegram"] == "customer"
    assert order["city"] is None


@pytest.mark.asyncio
async def test_miniapp_order_rejects_missing_rate_pair_before_save(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "RUB",
            "amountSell": 10000,
            "currencyBuy": "EUR",
            "amountBuy": 100,
            "rate": 0.01,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "RATE_PAIR_UNAVAILABLE"


@pytest.mark.asyncio
async def test_miniapp_order_cash_requires_city_and_uses_same_backend_validation(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    invalid_response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "georgia",
            "currencySell": "rub",
            "amountSell": 10000,
            "currencyBuy": "gel",
            "amountBuy": 300,
            "rate": 0.03,
            "methodGet": "cash",
        },
    )

    assert invalid_response.status_code == 422
    assert invalid_response.json()["code"] == "CITY_REQUIRED_FOR_CASH"

    response = await client.post(
        "/api/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "CityId": city.id,
            "country": "thailand",
            "currencySell": "rub",
            "amountSell": 10000,
            "currencyBuy": "thb",
            "amountBuy": 4000,
            "rate": 0.4,
            "methodGet": "cash",
        },
    )

    assert response.status_code == 201
    order = response.json()
    assert order["CityId"] == city.id
    assert order["country"] == "thailand"
    assert order["currencyBuy"] == "THB"
    assert order["methodGet"] == "cash"
    assert order["contactTelegram"] == "customer"


@pytest.mark.asyncio
async def test_miniapp_order_returns_machine_readable_errors(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    db_session.add(
        Order(
            UserId=customer.id,
            CityId=city.id,
            country=Country.THAILAND,
            currencySell="RUB",
            amountSell=1000,
            currencyBuy="THB",
            amountBuy=410,
            rate=0.41,
            status=int(OrderStatus.CREATED),
            methodGet="cash",
        )
    )
    await db_session.flush()

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "RUB",
            "amountSell": 1000,
            "currencyBuy": "EUR",
            "amountBuy": 100,
            "rate": 0.1,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ORDER_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_miniapp_order_requires_trusted_contact_readiness(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    city = City(name="Bangkok", country=Country.THAILAND)
    manager = User(
        telegram_id=700001,
        username="manager",
        first_name="Order",
        role=int(UserRole.MANAGER),
    )
    customer = User(
        telegram_id=700002,
        username=None,
        phone=None,
        first_name="Happy",
        role=int(UserRole.USER),
    )
    db_session.add_all(
        [
            city,
            manager,
            customer,
            Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND),
        ]
    )
    await db_session.flush()
    manager.city_id = city.id
    await db_session.flush()
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "RUB",
            "amountSell": 1000,
            "currencyBuy": "THB",
            "amountBuy": 400,
            "rate": 0.4,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "TRUSTED_CONTACT_NOT_READY"


@pytest.mark.asyncio
async def test_admin_summary_returns_mvp_dashboard_metrics(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all(
        [
            admin,
            Order(
                UserId=customer.id,
                CityId=city.id,
                country=Country.THAILAND,
                currencySell="RUB",
                amountSell=10000,
                currencyBuy="THB",
                amountBuy=4100,
                rate=0.41,
                status=int(OrderStatus.CREATED),
                methodGet="cash",
            ),
        ]
    )
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.get(
        "/api/admin/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["ordersToday"] == 1
    assert summary["usersTotal"] == 2
    assert summary["featuredRates"][0]["pairId"] == "rub-thb"
    assert summary["featuredRates"][0]["finalRateDisplay"] == "2.51"


def test_admin_summary_today_start_uses_configured_timezone() -> None:
    today_start = get_today_start_for_timezone(
        "Asia/Bangkok",
        now=datetime(2026, 5, 7, 17, 30, tzinfo=UTC),
    )

    assert today_start == datetime(2026, 5, 7, 17, 0, tzinfo=UTC)
