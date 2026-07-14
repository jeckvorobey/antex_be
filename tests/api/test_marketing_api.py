from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.order import OrderStatus
from app.models.admin import Admin
from app.models.marketing import (
    MarketingAttribution,
    MarketingCampaign,
    MarketingCurrency,
    MarketingPlatform,
)
from app.models.order import Order
from app.repositories.user import UserRepository


@pytest.fixture
async def marketing_api_client(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession, str]]:
    from app.main import app

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    admin = Admin(username="marketing-admin", password_hash="unused")
    db_session.add_all(
        [
            admin,
            MarketingPlatform(slug="telegram_ads", name="Telegram Ads"),
            MarketingCurrency(code="USDT", name="USDT"),
            MarketingCurrency(code="RUB", name="Russian Ruble"),
        ]
    )
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})
    settings.telegram_bot_username = "antex_test_bot"
    app.dependency_overrides[deps.get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session, token

    app.dependency_overrides.clear()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_campaign(client: AsyncClient, token: str, **overrides):
    payload = {
        "name": "Telegram July",
        "provider": "telegram_ads",
        "status": "active",
        "budget": 1500,
        "currency": "USDT",
    }
    payload.update(overrides)
    return await client.post(
        "/api/admin/marketing/campaigns",
        headers=auth(token),
        json=payload,
    )


async def test_campaign_api_requires_admin_and_generates_code_and_link(
    marketing_api_client,
) -> None:
    client, _, token = marketing_api_client
    unauthorized = await client.get("/api/admin/marketing/campaigns")
    response = await create_campaign(client, token)

    assert unauthorized.status_code == 401
    assert response.status_code == 201, response.text
    data = response.json()
    assert len(data["code"]) == 10
    assert data["code"].isalnum() and data["code"].isupper()
    assert data["link"] == f"https://t.me/antex_test_bot?startapp=market_{data['code']}"
    assert data["marketParameter"] == f"market={data['code']}"
    assert "source" not in data
    assert data["campaignType"] == "paid"


async def test_reference_endpoints_require_admin_and_reject_duplicates(
    marketing_api_client,
) -> None:
    client, _, token = marketing_api_client

    unauthorized = await client.get("/api/admin/marketing/platforms")
    platforms = await client.get("/api/admin/marketing/platforms", headers=auth(token))
    created = await client.post(
        "/api/admin/marketing/platforms",
        headers=auth(token),
        json={"slug": "google_ads", "name": "Google Ads"},
    )
    duplicate = await client.post(
        "/api/admin/marketing/platforms",
        headers=auth(token),
        json={"slug": "google_ads", "name": "Google Ads"},
    )

    assert unauthorized.status_code == 401
    assert platforms.json() == [{"slug": "telegram_ads", "name": "Telegram Ads"}]
    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "MARKETING_PLATFORM_ALREADY_EXISTS"


async def test_platform_soft_deletes_when_used_and_currency_requires_no_campaigns(
    marketing_api_client,
) -> None:
    client, _, token = marketing_api_client
    await create_campaign(client, token)

    platform = await client.delete(
        "/api/admin/marketing/platforms/telegram_ads", headers=auth(token)
    )
    currency = await client.delete("/api/admin/marketing/currencies/USDT", headers=auth(token))
    visible_platforms = await client.get("/api/admin/marketing/platforms", headers=auth(token))

    assert platform.status_code == 204
    assert currency.status_code == 409
    assert visible_platforms.json() == []


async def test_campaign_create_and_patch_reject_immutable_or_invalid_fields(
    marketing_api_client,
) -> None:
    client, _, token = marketing_api_client
    with_code = await create_campaign(client, token, code="BDF7J9J8JH")
    bad_provider = await create_campaign(client, token, provider="unknown")
    created = (await create_campaign(client, token)).json()
    immutable = await client.patch(
        f"/api/admin/marketing/campaigns/{created['id']}",
        headers=auth(token),
        json={"code": "AAAAAAAAAA", "provider": "other"},
    )
    updated = await client.patch(
        f"/api/admin/marketing/campaigns/{created['id']}",
        headers=auth(token),
        json={"name": "Updated", "status": "archived"},
    )

    assert with_code.status_code == 422
    assert bad_provider.status_code == 422
    assert immutable.status_code == 422
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated"
    assert updated.json()["status"] == "archived"


async def test_campaign_list_has_server_pagination_and_filters(marketing_api_client) -> None:
    client, _, token = marketing_api_client
    await create_campaign(client, token, name="Alpha", status="active")
    await create_campaign(client, token, name="Beta", status="paused")

    response = await client.get(
        "/api/admin/marketing/campaigns",
        headers=auth(token),
        params={"search": "Alpha", "provider": "telegram_ads", "status": "active", "limit": 1},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 0
    assert response.json()["items"][0]["name"] == "Alpha"

    missing = await client.get(
        "/api/admin/marketing/campaigns/9999",
        headers=auth(token),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "MARKETING_CAMPAIGN_NOT_FOUND"


async def test_daily_metrics_upsert_and_validation(marketing_api_client) -> None:
    client, _, token = marketing_api_client
    campaign = (await create_campaign(client, token)).json()
    url = f"/api/admin/marketing/campaigns/{campaign['id']}/daily-metrics/2026-07-13"

    created = await client.put(
        url,
        headers=auth(token),
        json={"impressions": 1000, "starts": 25, "spend": 40, "platformCpm": 4},
    )
    updated = await client.put(
        url,
        headers=auth(token),
        json={"impressions": 2000, "starts": 50, "spend": 60},
    )
    invalid = await client.put(
        url,
        headers=auth(token),
        json={"impressions": -1, "starts": 0, "spend": 0},
    )

    assert created.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["impressions"] == 2000
    assert updated.json()["spend"] == 60
    assert invalid.status_code == 422


async def test_applications_and_dashboard_use_post_attribution_orders(marketing_api_client) -> None:
    client, db_session, token = marketing_api_client
    campaign_data = (await create_campaign(client, token)).json()
    campaign = await db_session.get(MarketingCampaign, campaign_data["id"])
    assert campaign is not None
    user, _ = await UserRepository(db_session).find_or_create(777001, first_name="Applicant")
    attributed_at = datetime.now(UTC) - timedelta(days=2)
    db_session.add(
        MarketingAttribution(
            user_id=user.id,
            campaign_id=campaign.id,
            attributed_at=attributed_at,
        )
    )
    db_session.add_all(
        [
            _order(user.id, "PRE0000001", attributed_at - timedelta(hours=1)),
            _order(user.id, "POST000001", attributed_at + timedelta(hours=1)),
            _order(
                user.id,
                "POST000002",
                attributed_at + timedelta(days=1),
                status=OrderStatus.COMPLETED,
            ),
        ]
    )
    await db_session.flush()
    params = {"dateFrom": str(date.today() - timedelta(days=5)), "dateTo": str(date.today())}

    applications = await client.get(
        "/api/admin/marketing/applications",
        headers=auth(token),
        params=params,
    )
    dashboard = await client.get(
        "/api/admin/marketing/dashboard",
        headers=auth(token),
        params={**params, "currency": "USDT"},
    )

    assert applications.status_code == 200, applications.text
    row = applications.json()["items"][0]
    assert row["applications"] == 2
    assert row["uniqueApplicants"] == 1
    assert row["completedApplications"] == 1
    assert dashboard.status_code == 200, dashboard.text
    summary = dashboard.json()["summary"]
    assert summary["attributedUsers"] == 1
    assert summary["applications"] == 2
    assert summary["attributionToApplicationRate"] == 100
    assert summary["applicationCompletionRate"] == 50
    assert len(dashboard.json()["timeSeries"]) == 6


async def test_dashboard_empty_period_returns_null_rates_and_rejects_bad_dates(
    marketing_api_client,
) -> None:
    client, _, token = marketing_api_client
    empty = await client.get(
        "/api/admin/marketing/dashboard",
        headers=auth(token),
        params={"dateFrom": "2026-07-01", "dateTo": "2026-07-02"},
    )
    invalid = await client.get(
        "/api/admin/marketing/dashboard",
        headers=auth(token),
        params={"dateFrom": "2026-07-03", "dateTo": "2026-07-02"},
    )

    assert empty.status_code == 200
    assert empty.json()["summary"]["attributionToApplicationRate"] is None
    assert empty.json()["summary"]["applicationCompletionRate"] is None
    assert invalid.status_code == 422


async def test_dashboard_does_not_merge_mixed_currency_or_claim_roas(
    marketing_api_client,
) -> None:
    client, _, token = marketing_api_client
    usdt = (await create_campaign(client, token, name="USDT", currency="USDT")).json()
    rub = (await create_campaign(client, token, name="RUB", currency="RUB")).json()
    for campaign, spend in ((usdt, 10), (rub, 5000)):
        response = await client.put(
            f"/api/admin/marketing/campaigns/{campaign['id']}/daily-metrics/{date.today()}",
            headers=auth(token),
            json={"impressions": 100, "starts": 5, "spend": spend},
        )
        assert response.status_code == 200

    dashboard = await client.get(
        "/api/admin/marketing/dashboard",
        headers=auth(token),
        params={"dateFrom": str(date.today()), "dateTo": str(date.today())},
    )

    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["summary"]["spendTotal"] is None
    assert {item["currency"] for item in data["spendByCurrency"]} == {"RUB", "USDT"}
    assert "roas" not in str(data).lower()
    assert "roi" not in str(data).lower()


async def test_dashboard_query_count_is_bounded(marketing_api_client) -> None:
    client, db_session, token = marketing_api_client
    statements: list[str] = []

    def track_query(*args) -> None:
        statements.append(args[2])

    assert db_session.bind is not None
    event.listen(db_session.bind.sync_engine, "before_cursor_execute", track_query)
    try:
        response = await client.get(
            "/api/admin/marketing/dashboard",
            headers=auth(token),
            params={"dateFrom": str(date.today()), "dateTo": str(date.today())},
        )
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", track_query)

    assert response.status_code == 200
    assert len(statements) <= 8


def _order(
    user_id: int,
    public_number: str,
    created_at: datetime,
    *,
    status: OrderStatus = OrderStatus.CREATED,
) -> Order:
    return Order(
        UserId=user_id,
        country=Country.THAILAND,
        currencySell="USDT",
        amountSell=100,
        currencyBuy="RUB",
        amountBuy=9000,
        rate=90,
        status=int(status),
        methodGet="cash",
        publicNumber=public_number,
        createdAt=created_at,
        updatedAt=created_at,
    )
