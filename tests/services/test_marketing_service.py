from __future__ import annotations

import pytest
from sqlalchemy import select

from app.exceptions import AntExException
from app.models.marketing import MarketingCampaign, MarketingCurrency, MarketingPlatform
from app.modules.marketing.service import MarketingService
from app.repositories.user import UserRepository


async def _user(db_session, telegram_id: int):
    user, _ = await UserRepository(db_session).find_or_create(
        telegram_id,
        username=f"user_{telegram_id}",
        first_name="Test",
    )
    return user


async def _campaign(db_session, code: str, status: str = "active") -> MarketingCampaign:
    platform = await db_session.scalar(
        select(MarketingPlatform).where(MarketingPlatform.slug == "telegram_ads")
    )
    if platform is None:
        platform = MarketingPlatform(slug="telegram_ads", name="Telegram Ads")
        db_session.add(platform)
    currency = await db_session.scalar(
        select(MarketingCurrency).where(MarketingCurrency.code == "USDT")
    )
    if currency is None:
        currency = MarketingCurrency(code="USDT", name="USDT")
        db_session.add(currency)
    await db_session.flush()
    campaign = MarketingCampaign(
        code=code,
        name=f"Campaign {code}",
        platform_id=platform.id,
        currency_id=currency.id,
        status=status,
    )
    db_session.add(campaign)
    await db_session.flush()
    return campaign


async def test_first_touch_is_idempotent_and_does_not_overwrite(db_session) -> None:
    user = await _user(db_session, 101)
    first = await _campaign(db_session, "AAAAAAAAAA")
    second = await _campaign(db_session, "BBBBBBBBBB")
    service = MarketingService(db_session)

    attribution = await service.attribute_user(user.id, first.code)
    repeated = await service.attribute_user(user.id, first.code)
    other = await service.attribute_user(user.id, second.code)

    assert attribution.id == repeated.id == other.id
    assert other.campaign_id == first.id


@pytest.mark.parametrize(
    ("code", "status", "expected_code"),
    [
        ("UNKNOWN000", None, "MARKETING_CAMPAIGN_NOT_FOUND"),
        ("ARCHIVED00", "archived", "MARKETING_CAMPAIGN_INACTIVE"),
    ],
)
async def test_unknown_or_archived_campaign_is_rejected(
    db_session,
    code: str,
    status: str | None,
    expected_code: str,
) -> None:
    user = await _user(db_session, 202)
    if status is not None:
        await _campaign(db_session, code, status)

    with pytest.raises(AntExException) as error:
        await MarketingService(db_session).attribute_user(user.id, code)

    assert error.value.code == expected_code


async def test_invalid_marketing_code_is_rejected(db_session) -> None:
    user = await _user(db_session, 303)

    with pytest.raises(AntExException) as error:
        await MarketingService(db_session).attribute_user(user.id, "bad-code")

    assert error.value.code == "INVALID_MARKETING_CODE"
