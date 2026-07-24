from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.exceptions import AntExException
from app.models.attribution import MarketingTouch, UserAcquisition
from app.models.marketing import MarketingCampaign, MarketingCurrency, MarketingPlatform
from app.models.user import User
from app.repositories.user import UserRepository


async def _campaign(db_session, code: str) -> MarketingCampaign:
    platform = MarketingPlatform(slug=f"p_{code}", name=f"P {code}")
    currency = MarketingCurrency(code=f"X{code[:7]}", name=code)
    db_session.add_all([platform, currency])
    await db_session.flush()
    campaign = MarketingCampaign(
        code=code, name=code, platform_id=platform.id, currency_id=currency.id, status="active"
    )
    db_session.add(campaign)
    await db_session.flush()
    return campaign


async def test_existing_user_cannot_receive_referrer_from_public_start_param(
    db_session, monkeypatch
) -> None:
    from app.services import auth

    referrer = User(telegram_id=1, referral_code="ABCD1234")
    existing = User(telegram_id=2)
    db_session.add_all([referrer, existing])
    await db_session.flush()
    monkeypatch.setattr(
        auth,
        "validate_telegram_init_data",
        lambda _: {"user": '{"id": 2}', "start_param": "ref_ABCD1234"},
    )

    await auth.telegram_auth(db_session, "trusted")

    await db_session.refresh(existing)
    acquisition = await db_session.scalar(
        select(UserAcquisition.referrer_user_id).where(
            UserAcquisition.user_id == existing.id,
            UserAcquisition.source_type == "referral",
        )
    )
    assert acquisition is None


async def test_existing_acquired_user_cannot_bind_referrer_through_public_service(
    db_session,
) -> None:
    from app.services.referral import ReferralService

    referrer = User(telegram_id=21, referral_code="PUBLIC01")
    existing = User(telegram_id=22)
    db_session.add_all([referrer, existing])
    await db_session.flush()
    db_session.add(UserAcquisition(user_id=existing.id, source_type="direct"))
    await db_session.flush()

    with pytest.raises(AntExException) as error:
        await ReferralService().bind_referral(db_session, existing, "PUBLIC01")

    assert error.value.code == "REFERRAL_EXISTING_USER"
    acquisition = await db_session.scalar(
        select(UserAcquisition.referrer_user_id).where(
            UserAcquisition.user_id == existing.id,
            UserAcquisition.source_type == "referral",
        )
    )
    assert acquisition is None


async def test_referral_bind_replay_remains_idempotent_after_trusted_auth(
    db_session,
) -> None:
    from app.services.referral import ReferralService

    referrer = User(telegram_id=23, referral_code="REPLAY01")
    referred = User(telegram_id=24)
    db_session.add_all([referrer, referred])
    await db_session.flush()
    db_session.add(
        UserAcquisition(
            user_id=referred.id,
            source_type="referral",
            referrer_user_id=referrer.id,
        )
    )
    await db_session.flush()

    with pytest.raises(AntExException) as error:
        await ReferralService().bind_referral(db_session, referred, referrer.referral_code)

    assert error.value.code == "REFERRAL_EXISTING_USER"


async def test_new_user_receives_referrer_and_referral_acquisition(db_session, monkeypatch) -> None:
    from app.services import auth
    from app.services.attribution import AttributionService

    referrer = User(telegram_id=101, referral_code="NEWREF01")
    db_session.add(referrer)
    await db_session.flush()
    monkeypatch.setattr(
        auth,
        "validate_telegram_init_data",
        lambda _: {"user": '{"id": 102}', "start_param": "ref_NEWREF01"},
    )

    await auth.telegram_auth(db_session, "trusted")

    user = await UserRepository(db_session).get_by_telegram_id(102)
    assert user is not None
    acquisition = await AttributionService(db_session).get_acquisition(user.id)
    assert acquisition is not None
    assert acquisition.source_type == "referral"
    assert acquisition.referrer_user_id == referrer.id


async def test_campaign_registration_never_sets_referrer(db_session, monkeypatch) -> None:
    from app.services import auth
    from app.services.attribution import AttributionService

    campaign = await _campaign(db_session, "CAMPAIGN01")
    monkeypatch.setattr(
        auth,
        "validate_telegram_init_data",
        lambda _: {"user": '{"id": 103}', "start_param": "market_CAMPAIGN01"},
    )

    await auth.telegram_auth(db_session, "trusted")

    user = await UserRepository(db_session).get_by_telegram_id(103)
    assert user is not None
    referral_acq = await db_session.scalar(
        select(UserAcquisition.referrer_user_id).where(
            UserAcquisition.user_id == user.id,
            UserAcquisition.source_type == "referral",
        )
    )
    assert referral_acq is None
    acquisition = await AttributionService(db_session).get_acquisition(user.id)
    assert acquisition is not None
    assert acquisition.source_type == "campaign"
    assert acquisition.campaign_id == campaign.id


async def test_replayed_trusted_init_data_deduplicates_marketing_touch(
    db_session, monkeypatch
) -> None:
    from app.services import auth

    await _campaign(db_session, "REPLAY0001")
    parsed = {
        "user": '{"id": 104}',
        "start_param": "market_REPLAY0001",
        "query_id": "trusted-query-id",
        "auth_date": "1784640000",
    }
    monkeypatch.setattr(auth, "validate_telegram_init_data", lambda _: parsed)

    await auth.telegram_auth(db_session, "trusted")
    await auth.telegram_auth(db_session, "trusted")

    touches = (await db_session.execute(select(MarketingTouch))).scalars().all()
    assert len(touches) == 1
    assert touches[0].session_key is not None


async def test_invalid_campaign_keeps_auth_and_records_direct_acquisition(
    db_session, monkeypatch
) -> None:
    from app.services import auth
    from app.services.attribution import AttributionService

    monkeypatch.setattr(
        auth,
        "validate_telegram_init_data",
        lambda _: {"user": '{"id": 3}', "start_param": "market_UNKNOWN000"},
    )

    await auth.telegram_auth(db_session, "trusted")

    user = await UserRepository(db_session).get_by_telegram_id(3)
    assert user is not None
    acquisition = await AttributionService(db_session).get_acquisition(user.id)
    assert acquisition is not None and acquisition.source_type == "direct"


async def test_campaign_touches_do_not_overwrite_referral_acquisition(db_session) -> None:
    from app.services.attribution import AttributionService

    referrer = User(telegram_id=10)
    user = User(telegram_id=11)
    db_session.add_all([referrer, user])
    await db_session.flush()
    campaign = await _campaign(db_session, "AAAAAAAAAA")

    service = AttributionService(db_session)
    await service.ensure_acquisition(user.id, source_type="referral", referrer_user_id=referrer.id)
    touch = await service.record_marketing_touch(
        user.id,
        campaign.code,
        is_new_user=False,
        session_key="referral-campaign-touch",
    )

    acquisition = await service.get_acquisition(user.id)
    assert acquisition is not None and acquisition.source_type == "referral"
    assert touch.user_state == "returning"


async def test_repeated_touch_for_primary_campaign_stays_new_for_that_campaign(db_session) -> None:
    from app.services.attribution import AttributionService

    user, _ = await UserRepository(db_session).find_or_create(13)
    campaign = await _campaign(db_session, "PRIMARY000")
    service = AttributionService(db_session)
    await service.ensure_acquisition(user.id, source_type="campaign", campaign_id=campaign.id)

    touch = await service.record_marketing_touch(
        user.id,
        campaign.code,
        is_new_user=False,
        session_key="primary-campaign-repeat",
    )

    assert touch.user_state == "new"


async def test_touch_for_another_campaign_remains_returning(db_session) -> None:
    from app.services.attribution import AttributionService

    user, _ = await UserRepository(db_session).find_or_create(14)
    primary = await _campaign(db_session, "PRIMARY000")
    another = await _campaign(db_session, "ANOTHER000")
    service = AttributionService(db_session)
    await service.ensure_acquisition(user.id, source_type="campaign", campaign_id=primary.id)

    touch = await service.record_marketing_touch(
        user.id,
        another.code,
        is_new_user=False,
        session_key="another-campaign-touch",
    )

    assert touch.user_state == "returning"


async def test_marketing_touch_requires_trusted_session_key(db_session) -> None:
    from app.services.attribution import AttributionService

    user, _ = await UserRepository(db_session).find_or_create(12)
    campaign = await _campaign(db_session, "SESSION0001")

    with pytest.raises(ValueError, match="MARKETING_SESSION_KEY_REQUIRED"):
        await AttributionService(db_session).record_marketing_touch(
            user.id,
            campaign.code,
            is_new_user=False,
        )


async def test_last_touch_within_window_creates_reengagement_snapshot(db_session) -> None:
    from app.services.attribution import AttributionService

    user, _ = await UserRepository(db_session).find_or_create(20)
    first = await _campaign(db_session, "BBBBBBBBBB")
    second = await _campaign(db_session, "CCCCCCCCCC")
    service = AttributionService(db_session)
    await service.ensure_acquisition(user.id, source_type="direct")
    await service.record_marketing_touch(
        user.id,
        first.code,
        is_new_user=False,
        touched_at=datetime.now(UTC) - timedelta(days=2),
        session_key="old-touch",
    )
    last = await service.record_marketing_touch(
        user.id,
        second.code,
        is_new_user=False,
        session_key="last-touch",
    )

    result = await service.resolve_order_attribution(user.id, datetime.now(UTC), 7)

    assert result.marketing_touch_id == last.id
    assert result.campaign_id == second.id
    assert result.attribution_type == "reengagement"
    touches = (
        (await db_session.execute(select(MarketingTouch).where(MarketingTouch.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(touches) == 2


async def test_touch_outside_window_has_none_attribution(db_session) -> None:
    from app.services.attribution import AttributionService

    user, _ = await UserRepository(db_session).find_or_create(30)
    campaign = await _campaign(db_session, "DDDDDDDDDD")
    service = AttributionService(db_session)
    await service.ensure_acquisition(user.id, source_type="direct")
    await service.record_marketing_touch(
        user.id,
        campaign.code,
        is_new_user=False,
        touched_at=datetime.now(UTC) - timedelta(days=8),
        session_key="outside-window",
    )

    result = await service.resolve_order_attribution(user.id, datetime.now(UTC), 7)

    assert result.attribution_type == "none"
    assert result.campaign_id is None
