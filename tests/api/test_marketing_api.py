from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.order import OrderStatus
from app.models.admin import Admin
from app.models.attribution import MarketingTouch, OrderAttribution, UserAcquisition
from app.models.marketing import (
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


async def test_campaign_code_preview_is_unique_and_does_not_persist(
    marketing_api_client,
) -> None:
    """Preview-код выдаётся сервером, но не создаёт черновик кампании в БД."""
    client, db_session, token = marketing_api_client

    unauthorized = await client.post("/api/admin/marketing/campaigns/code-preview")
    response = await client.post(
        "/api/admin/marketing/campaigns/code-preview",
        headers=auth(token),
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200, response.text
    code = response.json()["code"]
    assert response.json()["token"]
    assert len(code) == 10
    assert code.isalnum() and code.isupper()
    assert (
        await db_session.scalar(select(MarketingCampaign).where(MarketingCampaign.code == code))
        is None
    )


async def test_marketing_endpoints_reject_admin_refresh_token(marketing_api_client) -> None:
    """Refresh-токен нельзя использовать для preview или создания кампании."""
    client, db_session, _ = marketing_api_client
    admin_id = await db_session.scalar(select(Admin.id).where(Admin.username == "marketing-admin"))
    refresh_token = create_access_token({"sub": str(admin_id), "type": "admin_refresh"})

    preview = await client.post(
        "/api/admin/marketing/campaigns/code-preview",
        headers=auth(refresh_token),
    )
    created = await create_campaign(client, refresh_token)

    assert preview.status_code == 403
    assert created.status_code == 403


async def test_campaign_create_persists_preview_code_only_after_full_validation(
    marketing_api_client,
) -> None:
    """Показанный код попадает в БД только после полной валидации кампании."""
    client, db_session, token = marketing_api_client
    preview = await client.post(
        "/api/admin/marketing/campaigns/code-preview",
        headers=auth(token),
    )
    code = preview.json()["code"]
    code_token = preview.json()["token"]

    invalid = await create_campaign(
        client,
        token,
        codeToken=code_token,
        startsAt="2026-07-20",
        endsAt="2026-07-19",
    )
    assert invalid.status_code == 422
    assert (
        await db_session.scalar(select(MarketingCampaign).where(MarketingCampaign.code == code))
        is None
    )

    created = await create_campaign(client, token, codeToken=code_token)
    assert created.status_code == 201, created.text
    assert created.json()["code"] == code
    assert (
        await db_session.scalar(select(MarketingCampaign).where(MarketingCampaign.code == code))
        is not None
    )

    duplicate = await create_campaign(client, token, codeToken=code_token, name="Duplicate")
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "MARKETING_CODE_ALREADY_EXISTS"


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


async def test_campaign_create_rejects_direct_code_and_patch_immutable_fields(
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


async def test_campaign_detail_and_update_include_current_aggregates(
    marketing_api_client,
) -> None:
    client, db_session, token = marketing_api_client
    campaign_data = (await create_campaign(client, token)).json()
    user, _ = await UserRepository(db_session).find_or_create(777000, first_name="Detail")
    db_session.add(
        UserAcquisition(
            user_id=user.id,
            source_type="campaign",
            campaign_id=campaign_data["id"],
        )
    )
    await db_session.flush()

    detail = await client.get(
        f"/api/admin/marketing/campaigns/{campaign_data['id']}",
        headers=auth(token),
    )
    updated = await client.patch(
        f"/api/admin/marketing/campaigns/{campaign_data['id']}",
        headers=auth(token),
        json={"name": "Updated metrics"},
    )

    assert detail.status_code == 200, detail.text
    assert detail.json()["newUsers"] == 1
    assert detail.json()["attributedUsers"] == 1
    assert updated.status_code == 200, updated.text
    assert updated.json()["newUsers"] == 1
    assert updated.json()["attributedUsers"] == 1


async def test_campaign_create_rejects_non_preview_token(marketing_api_client) -> None:
    """Обычный access token нельзя использовать вместо подписанного preview token."""
    client, _, token = marketing_api_client

    response = await create_campaign(client, token, codeToken=token)

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_MARKETING_CODE_PREVIEW"


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


async def test_campaign_list_hides_archived_by_default_and_includes_them_on_request(
    marketing_api_client,
) -> None:
    client, _, token = marketing_api_client
    await create_campaign(client, token, name="Active", status="active")
    await create_campaign(client, token, name="Archived", status="archived")

    default_response = await client.get(
        "/api/admin/marketing/campaigns",
        headers=auth(token),
    )
    with_archive_response = await client.get(
        "/api/admin/marketing/campaigns",
        headers=auth(token),
        params={"include_archived": "true"},
    )

    assert default_response.status_code == 200
    assert default_response.json()["total"] == 1
    assert [item["name"] for item in default_response.json()["items"]] == ["Active"]
    assert with_archive_response.status_code == 200
    assert with_archive_response.json()["total"] == 2
    assert {item["name"] for item in with_archive_response.json()["items"]} == {
        "Active",
        "Archived",
    }


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


async def test_applications_and_dashboard_use_order_attribution_snapshots(
    marketing_api_client,
) -> None:
    client, db_session, token = marketing_api_client
    campaign_data = (await create_campaign(client, token)).json()
    campaign = await db_session.get(MarketingCampaign, campaign_data["id"])
    assert campaign is not None
    user, _ = await UserRepository(db_session).find_or_create(777001, first_name="Applicant")
    attributed_at = datetime.now(UTC) - timedelta(days=2)
    acquisition = UserAcquisition(
        user_id=user.id,
        source_type="campaign",
        campaign_id=campaign.id,
        acquired_at=attributed_at,
    )
    new_touch = MarketingTouch(
        user_id=user.id,
        campaign_id=campaign.id,
        touched_at=attributed_at,
        user_state="new",
    )
    returning_touch = MarketingTouch(
        user_id=user.id,
        campaign_id=campaign.id,
        touched_at=attributed_at + timedelta(hours=12),
        user_state="returning",
    )
    first_order = _order(user.id, "POST000001", attributed_at + timedelta(hours=1))
    second_order = _order(
        user.id,
        "POST000002",
        attributed_at + timedelta(days=1),
        status=OrderStatus.COMPLETED,
    )
    db_session.add_all([acquisition, new_touch, returning_touch, first_order, second_order])
    await db_session.flush()
    db_session.add_all(
        [
            OrderAttribution(
                order_id=first_order.id,
                campaign_id=campaign.id,
                marketing_touch_id=new_touch.id,
                attribution_type="acquisition",
                attributed_at=new_touch.touched_at,
                lookback_days=7,
            ),
            OrderAttribution(
                order_id=second_order.id,
                campaign_id=campaign.id,
                marketing_touch_id=returning_touch.id,
                attribution_type="reengagement",
                attributed_at=returning_touch.touched_at,
                lookback_days=7,
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
    assert row["newUsers"] == 1
    assert row["returningUsers"] == 1
    assert row["touches"] == 2
    assert row["newUserApplications"] == 1
    assert row["returningUserApplications"] == 1
    assert row["uniqueApplicants"] == 1
    assert row["completedApplications"] == 1
    assert dashboard.status_code == 200, dashboard.text
    summary = dashboard.json()["summary"]
    assert summary["attributedUsers"] == 1
    assert summary["newUsers"] == 1
    assert summary["returningUsers"] == 1
    assert summary["touches"] == 2
    assert summary["applications"] == 2
    assert summary["attributionToApplicationRate"] == 100
    assert summary["applicationCompletionRate"] == 50
    time_series = dashboard.json()["timeSeries"]
    assert len(time_series) == 6
    assert sum(item["newUsers"] for item in time_series) == 1
    assert sum(item["returningUsers"] for item in time_series) == 1
    assert sum(item["touches"] for item in time_series) == 2

    campaigns = await client.get("/api/admin/marketing/campaigns", headers=auth(token))
    campaign_row = campaigns.json()["items"][0]
    assert campaign_row["attributedUsers"] == campaign_row["newUsers"] == 1
    assert campaign_row["returningUsers"] == 1
    assert campaign_row["touches"] == 2
    assert campaign_row["completedApplications"] == 1

    details = await client.get(
        "/api/admin/marketing/application-attributions",
        headers=auth(token),
        params=params,
    )
    assert details.status_code == 200, details.text
    assert details.json()["total"] == 2
    detail_rows = details.json()["items"]
    assert {item["attributionType"] for item in detail_rows} == {
        "acquisition",
        "reengagement",
    }
    assert all(item["touchAt"] and item["applicationAt"] for item in detail_rows)
    assert all(item["hoursToApplication"] >= 0 for item in detail_rows)


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

    too_large = await client.get(
        "/api/admin/marketing/dashboard",
        headers=auth(token),
        params={"dateFrom": "2025-01-01", "dateTo": "2026-07-02"},
    )
    assert too_large.status_code == 422
    assert too_large.json()["code"] == "MARKETING_DATE_RANGE_TOO_LARGE"

    overflowing = await client.get(
        "/api/admin/marketing/dashboard",
        headers=auth(token),
        params={"dateFrom": "9999-12-30", "dateTo": "9999-12-31"},
    )
    assert overflowing.status_code == 422
    assert overflowing.json()["code"] == "INVALID_MARKETING_DATE_RANGE"


async def test_dashboard_unique_touched_users_is_distinct_across_campaigns(
    marketing_api_client,
) -> None:
    client, db_session, token = marketing_api_client
    first = (await create_campaign(client, token, name="First")).json()
    second = (await create_campaign(client, token, name="Second")).json()
    user, _ = await UserRepository(db_session).find_or_create(778001, first_name="Shared")
    now = datetime.now(UTC)
    first_touch = MarketingTouch(
        user_id=user.id,
        campaign_id=first["id"],
        touched_at=now,
        user_state="returning",
    )
    second_touch = MarketingTouch(
        user_id=user.id,
        campaign_id=second["id"],
        touched_at=now,
        user_state="returning",
    )
    first_order = _order(user.id, "SHARED0001", now)
    second_order = _order(user.id, "SHARED0002", now)
    db_session.add_all([first_touch, second_touch, first_order, second_order])
    await db_session.flush()
    db_session.add_all(
        [
            OrderAttribution(
                order_id=first_order.id,
                campaign_id=first["id"],
                marketing_touch_id=first_touch.id,
                attribution_type="reengagement",
                attributed_at=now,
                lookback_days=7,
            ),
            OrderAttribution(
                order_id=second_order.id,
                campaign_id=second["id"],
                marketing_touch_id=second_touch.id,
                attribution_type="reengagement",
                attributed_at=now,
                lookback_days=7,
            ),
        ]
    )
    await db_session.flush()

    response = await client.get(
        "/api/admin/marketing/dashboard",
        headers=auth(token),
        # Dashboard applies date bounds in UTC, therefore the fixture and filter share UTC date.
        params={"dateFrom": str(now.date()), "dateTo": str(now.date()), "currency": "USDT"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["summary"]["touches"] == 2
    assert response.json()["summary"]["returningUsers"] == 1
    assert response.json()["summary"]["uniqueTouchedUsers"] == 1
    assert response.json()["summary"]["uniqueApplicants"] == 1


async def test_dashboard_reengagement_conversion_uses_unique_touched_users(
    marketing_api_client,
) -> None:
    client, db_session, token = marketing_api_client
    campaign_data = (await create_campaign(client, token)).json()
    user, _ = await UserRepository(db_session).find_or_create(777099, first_name="Returning")
    now = datetime.now(UTC)
    touched_at = now
    touch = MarketingTouch(
        user_id=user.id,
        campaign_id=campaign_data["id"],
        touched_at=touched_at,
        user_state="returning",
        session_key="dashboard-returning",
    )
    order = _order(user.id, "RETURN0001", now)
    db_session.add_all([touch, order])
    await db_session.flush()
    db_session.add(
        OrderAttribution(
            order_id=order.id,
            campaign_id=campaign_data["id"],
            marketing_touch_id=touch.id,
            attribution_type="reengagement",
            attributed_at=touched_at,
            lookback_days=7,
        )
    )
    await db_session.flush()

    response = await client.get(
        "/api/admin/marketing/dashboard",
        headers=auth(token),
        # Dashboard applies UTC calendar boundaries, not the local developer date.
        params={"dateFrom": str(now.date()), "dateTo": str(now.date()), "currency": "USDT"},
    )

    assert response.status_code == 200, response.text
    summary = response.json()["summary"]
    assert summary["attributedUsers"] == 0
    assert summary["uniqueTouchedUsers"] == 1
    assert summary["uniqueApplicants"] == 1
    assert summary["attributionToApplicationRate"] == 100


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
