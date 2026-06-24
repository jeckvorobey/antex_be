from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.user import UserRole
from app.models.admin import Admin
from app.models.city import City
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
async def test_admin_summary_returns_featured_rates(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    admin, _ = await seed_admin_exchange_data(db_session)
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.get(
        "/api/admin/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ordersToday"] == 0
    assert payload["usersTotal"] == 2
    assert payload["featuredRates"][0]["pairId"] == "rub-thb"
    assert payload["featuredRates"][0]["finalRateDisplay"] == "2.51"


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
