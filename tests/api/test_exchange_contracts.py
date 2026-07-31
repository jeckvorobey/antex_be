from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
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

    settings.jwt_secret = "test-secret-for-exchange-contracts"
    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session

    app.dependency_overrides.clear()


async def seed_admin_exchange_data(db_session: AsyncSession) -> tuple[Admin, User]:
    admin = Admin(username="admin", password_hash="x")
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
            admin,
            city,
            manager,
            customer,
            Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND),
            Rate(currency="RUBGEL", price=0.03, margin=3.0, country=Country.GEORGIA),
            Rate(currency="USDTTHB", price=36.2, margin=3.0, country=Country.THAILAND),
        ]
    )
    await db_session.flush()
    manager.city_id = city.id
    customer.city_id = city.id
    await db_session.commit()
    return admin, customer


@pytest.mark.asyncio
async def test_admin_rates_include_base_and_final_values(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    admin, _ = await seed_admin_exchange_data(db_session)
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.get(
        "/api/admin/rates",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    rows = response.json()
    rows_by_currency = {row["currency"]: row for row in rows}

    rub_thb = rows_by_currency["RUBTHB"]
    assert rub_thb["country"] == "thailand"
    assert rub_thb["countryRuName"] == "Таиланд"
    assert rub_thb["baseRate"] == pytest.approx(1 / 0.41)
    assert rub_thb["finalRate"] == pytest.approx(2.51)
    assert rub_thb["baseRateDisplay"] == "2.44"
    assert rub_thb["finalRateDisplay"] == "2.51"

    usdt_thb = rows_by_currency["USDTTHB"]
    assert usdt_thb["baseRate"] == pytest.approx(36.2)
    assert usdt_thb["finalRate"] == pytest.approx(35.11)
    assert usdt_thb["baseRateDisplay"] == "36.20"
    assert usdt_thb["finalRateDisplay"] == "35.11"

    rub_gel = rows_by_currency["RUBGEL"]
    assert rub_gel["country"] == "georgia"
    assert rub_gel["countryRuName"] == "Грузия"


@pytest.mark.asyncio
async def test_admin_create_normalizes_external_currency_to_uppercase(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Admin write сохраняет внешний код в canonical uppercase-форме."""
    client, db_session = api_client
    admin, _ = await seed_admin_exchange_data(db_session)
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.post(
        "/api/admin/rates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "currency": "usdtgel",
            "country": "georgia",
            "price": 2.7,
            "margin": 3.0,
        },
    )

    assert response.status_code == 201
    assert response.json()["currency"] == "USDTGEL"
    stored = await db_session.scalar(select(Rate).where(Rate.currency == "USDTGEL"))
    assert stored is not None


@pytest.mark.asyncio
async def test_admin_summary_returns_featured_rates(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    admin, customer = await seed_admin_exchange_data(db_session)
    now = datetime.now(UTC)
    customer.lastActiveAt = now
    db_session.add_all(
        [
            Rate(
                currency="USDTRUB",
                price=80,
                margin=4.5,
                country=None,
                is_internal=True,
            ),
            Order(
                UserId=customer.id,
                CityId=customer.city_id,
                country=Country.THAILAND,
                currencySell="USDT",
                amountSell=300,
                currencyBuy="THB",
                amountBuy=9081,
                rate=30.27,
                status=int(OrderStatus.CREATED),
                methodGet="qrcode",
                publicNumber="2026073101",
                createdAt=now - timedelta(minutes=45),
            ),
            Order(
                UserId=customer.id,
                CityId=customer.city_id,
                country=Country.THAILAND,
                currencySell="RUB",
                amountSell=10000,
                currencyBuy="THB",
                amountBuy=4100,
                rate=0.41,
                status=int(OrderStatus.COMPLETED),
                methodGet="cash",
                publicNumber="2026073102",
                endTime=now,
            ),
        ]
    )
    await db_session.commit()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.get(
        "/api/admin/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ordersToday"] == 2
    assert payload["usersTotal"] == 2
    assert payload["featuredRates"][0]["pairId"] == "rub-thb"
    assert payload["featuredRates"][0]["finalRateDisplay"] == "2.51"
    assert payload["users"] == {
        "total": 2,
        "newToday": 2,
        "activeToday": 1,
    }
    assert payload["orders"] == {
        "total": 2,
        "today": 2,
        "new": 1,
        "inProgress": 0,
        "completedToday": 1,
    }
    assert payload["attentionOrders"][0]["publicNumber"] == "2026073101"
    assert payload["attentionOrders"][0]["overdue"] is True
    assert payload["attentionOrders"][0]["reason"] == "Не обработана вовремя"  # noqa: RUF001
    assert len(payload["attentionOrders"]) <= 2
    turnover = {row["currency"]: row for row in payload["turnover"]}
    assert turnover["RUB"]["today"] == 10000
    assert turnover["THB"]["today"] == 4100
    assert len(payload["rates"]) == 4
    assert payload["rates"][0]["rateText"].startswith("1 ")
    assert any(rate["label"] == "USDT/RUB" for rate in payload["rates"])
    assert payload["generatedAt"]


@pytest.mark.asyncio
async def test_internal_rates_are_visible_only_in_admin_list(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Внутренние пары видны в admin list и скрыты от остальных readers."""
    client, db_session = api_client
    admin, customer = await seed_admin_exchange_data(db_session)
    internal = Rate(currency="USDTRUB", price=90.0, margin=4.5, country=None, is_internal=True)
    inverse = Rate(
        currency="RUBUSDT",
        price=1 / 90.0,
        margin=3.0,
        country=None,
        is_internal=True,
    )
    db_session.add_all([internal, inverse])
    await db_session.commit()

    admin_token = create_access_token({"sub": str(admin.id), "type": "admin"})
    user_token = create_access_token({"sub": str(customer.id), "role": customer.role})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    public_response = await client.get("/public/rates")
    miniapp_response = await client.get("/api/miniapp/rates", headers=user_headers)
    admin_response = await client.get("/api/admin/rates", headers=admin_headers)
    detail_response = await client.get(f"/api/admin/rates/{internal.id}", headers=admin_headers)
    patch_response = await client.patch(
        f"/api/admin/rates/{internal.id}",
        headers=admin_headers,
        json={"margin": 5.0},
    )
    protected_patch_response = await client.patch(
        f"/api/admin/rates/{internal.id}",
        headers=admin_headers,
        json={"price": 100.0},
    )
    delete_response = await client.delete(
        f"/api/admin/rates/{internal.id}",
        headers=admin_headers,
    )

    from app.services import rate_fetcher

    monkeypatch.setattr(
        rate_fetcher,
        "fetch_and_save_rates",
        AsyncMock(return_value={"USDTTHB": 36.0, "USDTRUB": 90.0, "RUBUSDT": 1 / 90.0}),
    )
    refresh_response = await client.post("/api/admin/rates/refresh", headers=admin_headers)

    assert public_response.status_code == 200
    assert miniapp_response.status_code == 200
    assert admin_response.status_code == 200
    assert {row["currency"] for row in public_response.json()} == {
        "RUBTHB",
        "RUBGEL",
        "USDTTHB",
    }
    assert {row["currency"] for row in miniapp_response.json()["items"]} == {
        "RUBTHB",
        "RUBGEL",
        "USDTTHB",
    }
    admin_rows = {row["currency"]: row for row in admin_response.json()}
    assert set(admin_rows) == {
        "RUBTHB",
        "RUBGEL",
        "USDTTHB",
        "USDTRUB",
        "RUBUSDT",
    }
    assert admin_rows["USDTRUB"]["country"] is None
    assert admin_rows["USDTRUB"]["countryRuName"] is None
    assert admin_rows["USDTRUB"]["isInternal"] is True
    assert admin_rows["RUBUSDT"]["isInternal"] is True
    assert admin_rows["RUBUSDT"]["baseRate"] == pytest.approx(1 / 90.0)
    assert admin_rows["RUBUSDT"]["baseRateDisplay"] == "0.011111"
    assert admin_rows["RUBUSDT"]["finalRate"] == pytest.approx(0.010778)
    assert admin_rows["RUBUSDT"]["finalRateDisplay"] == "0.010778"
    assert detail_response.status_code == 404
    assert patch_response.status_code == 200
    assert patch_response.json()["margin"] == 5.0
    assert patch_response.json()["finalRate"] == pytest.approx(85.5)
    assert protected_patch_response.status_code == 422
    assert delete_response.status_code == 404
    assert refresh_response.status_code == 200
    assert set(refresh_response.json()["rates"]) == {"USDTTHB"}


@pytest.mark.asyncio
@pytest.mark.parametrize("reserved_currency", ["USDTRUB", "rubusdt"])
async def test_admin_cannot_create_reserved_internal_rate(
    api_client: tuple[AsyncClient, AsyncSession],
    reserved_currency: str,
) -> None:
    """Admin API не создаёт внешнюю строку, использующую внутренний код."""
    client, db_session = api_client
    admin, _ = await seed_admin_exchange_data(db_session)
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.post(
        "/api/admin/rates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "currency": reserved_currency,
            "country": "thailand",
            "price": 90.0,
            "margin": 3.0,
        },
    )

    assert response.status_code == 422
    stored = await db_session.scalar(select(Rate).where(Rate.currency == reserved_currency.upper()))
    assert stored is None


@pytest.mark.asyncio
@pytest.mark.parametrize("reserved_currency", ["USDTRUB", "rubusdt"])
async def test_admin_cannot_rename_visible_rate_to_reserved_internal_rate(
    api_client: tuple[AsyncClient, AsyncSession],
    reserved_currency: str,
) -> None:
    """Admin API не переименовывает внешний курс во внутреннюю пару."""
    client, db_session = api_client
    admin, _ = await seed_admin_exchange_data(db_session)
    token = create_access_token({"sub": str(admin.id), "type": "admin"})
    visible = await db_session.scalar(select(Rate).where(Rate.currency == "USDTTHB"))
    assert visible is not None

    response = await client.patch(
        f"/api/admin/rates/{visible.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"currency": reserved_currency},
    )

    assert response.status_code == 422
    await db_session.refresh(visible)
    assert visible.currency == "USDTTHB"


@pytest.mark.asyncio
async def test_admin_cannot_assign_internal_country_to_external_entities(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Техническая страна доступна только заявкам внутреннего обмена."""
    client, db_session = api_client
    admin, _ = await seed_admin_exchange_data(db_session)
    token = create_access_token({"sub": str(admin.id), "type": "admin"})
    headers = {"Authorization": f"Bearer {token}"}
    visible_rate = await db_session.scalar(select(Rate).where(Rate.currency == "USDTTHB"))
    city = await db_session.scalar(select(City).where(City.name == "Bangkok"))
    assert visible_rate is not None
    assert city is not None

    create_city = await client.post(
        "/api/admin/cities",
        headers=headers,
        json={"name": "Internal", "country": "internal"},
    )
    update_city = await client.patch(
        f"/api/admin/cities/{city.id}",
        headers=headers,
        json={"country": "internal"},
    )
    create_rate = await client.post(
        "/api/admin/rates",
        headers=headers,
        json={"currency": "USDTXXX", "country": "internal", "price": 1.0},
    )
    update_rate = await client.patch(
        f"/api/admin/rates/{visible_rate.id}",
        headers=headers,
        json={"country": "internal"},
    )

    assert create_city.status_code == 422
    assert update_city.status_code == 422
    assert create_rate.status_code == 422
    assert update_rate.status_code == 422


@pytest.mark.asyncio
async def test_orders_api_accepts_preliminary_rate_and_amount_buy_fields(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, customer = await seed_admin_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "CityId": customer.city_id,
            "country": "thailand",
            "currencySell": "RUB",
            "amountSell": 30000,
            "currencyBuy": "THB",
            "amountBuy": 999999,
            "rate": 99,
            "methodGet": "cash",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["amountBuy"] == 999999
    assert payload["rate"] == 99
