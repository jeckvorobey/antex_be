from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.country import Country
from app.enums.user import UserRole
from app.exceptions import AntExException
from app.models.attribution import MarketingTouch, OrderAttribution
from app.models.city import City
from app.models.marketing import MarketingCampaign, MarketingCurrency, MarketingPlatform
from app.models.order import Order
from app.models.rate import Rate
from app.models.user import User
from app.repositories.config import ConfigRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.services import order_flow
from app.services.order_notifications import DeliveryOutcome, OrderCreatedDelivery


def _usdt_thb_rate() -> Rate:
    """Полная cash-фикстура для тестов, не проверяющих валютную политику."""
    return Rate(currency="USDTTHB", price=36.2, margin=3.0, country=Country.THAILAND)


@pytest.mark.asyncio
async def test_create_order_for_user_passes_global_manager_to_notification(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    rate = Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND)

    db_session.add_all([city, manager, customer, rate, _usdt_thb_rate()])
    await db_session.flush()

    customer.city_id = city.id
    await db_session.commit()

    notify_mock = AsyncMock()
    monkeypatch.setattr(order_flow, "notify_order_created", notify_mock)

    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        cityId=city.id,
        currencySell="RUB",
        amountSell=30000,
        currencyBuy="THB",
        amountBuy=12000,
        rate=0.4,
        methodGet="cash",
    )

    await order_flow.create_order_for_user(db_session, customer, payload)

    notify_mock.assert_awaited_once()
    _, _, notified_manager = notify_mock.await_args.args
    assert notified_manager is not None
    assert notified_manager.id == manager.id


@pytest.mark.asyncio
async def test_create_order_persists_server_quote_and_display_snapshot(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    city = City(name="Tbilisi", country=Country.GEORGIA)
    manager = User(telegram_id=700011, username="manager-ge", role=int(UserRole.MANAGER))
    customer = User(telegram_id=700012, username="customer-ge")
    rate = Rate(
        currency="RUBGEL",
        price=0.03,
        margin=3.0,
        country=Country.GEORGIA,
        display_reversed=True,
    )
    conversion_rate = Rate(
        currency="USDTGEL",
        price=2.7,
        margin=3.0,
        country=Country.GEORGIA,
    )
    db_session.add_all([city, manager, customer, rate, conversion_rate])
    await db_session.flush()
    customer.city_id = city.id
    await db_session.commit()
    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())

    created = await order_flow.create_order_for_user(
        db_session,
        customer,
        MiniappOrderCreate(
            country=Country.GEORGIA,
            cityId=city.id,
            currencySell="RUB",
            amountSell=30000,
            currencyBuy="GEL",
            amountBuy=999999,
            rate=99,
            methodGet="cash",
        ),
    )

    assert created.rate == pytest.approx(0.0291)
    assert created.deliveryRate == pytest.approx(0.0282)
    assert created.amountBuy == pytest.approx(846)
    assert created.displayRate == pytest.approx(35.4609929078)
    assert created.displayCurrencySell == "GEL"
    assert created.displayCurrencyBuy == "RUB"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_get", "amount_sell", "expected_delivery_rate"),
    [
        ("cash", 100_000, 0.4),
        ("qrcode", 30_000, None),
    ],
)
async def test_create_order_persists_delivery_rate_only_for_cash(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    method_get: str,
    amount_sell: int,
    expected_delivery_rate: float | None,
) -> None:
    """Неверная ветка persistence заполнит deliveryRate для другого метода или обнулит cash."""
    city = City(name=f"Bangkok-{method_get}", country=Country.THAILAND)
    customer = User(telegram_id=700020 + amount_sell, username=f"customer-{method_get}")
    rate = Rate(currency="RUBTHB", price=0.4, margin=0.0, country=Country.THAILAND)
    db_session.add_all([city, customer, rate])
    await db_session.flush()
    customer.city_id = city.id
    await db_session.commit()
    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())

    created = await order_flow.create_order_for_user(
        db_session,
        customer,
        MiniappOrderCreate(
            country=Country.THAILAND,
            cityId=city.id,
            currencySell="RUB",
            amountSell=amount_sell,
            currencyBuy="THB",
            amountBuy=1,
            rate=99,
            methodGet=method_get,
        ),
    )

    if expected_delivery_rate is None:
        assert created.deliveryRate is None
    else:
        assert created.deliveryRate == pytest.approx(expected_delivery_rate)
    assert created.rate == pytest.approx(0.4)
    assert created.amountBuy == pytest.approx(amount_sell * 0.4)


@pytest.mark.asyncio
async def test_create_order_recalculates_latest_rate_instead_of_client_quote(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Изменение Rates до submit должно заменить устаревшие клиентские значения."""
    city = City(name="Bangkok-latest", country=Country.THAILAND)
    customer = User(telegram_id=700099, username="customer-latest")
    rate = Rate(currency="RUBTHB", price=0.5, margin=0.0, country=Country.THAILAND)
    db_session.add_all([city, customer, rate])
    await db_session.flush()
    customer.city_id = city.id
    await db_session.commit()
    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())

    created = await order_flow.create_order_for_user(
        db_session,
        customer,
        MiniappOrderCreate(
            country=Country.THAILAND,
            cityId=city.id,
            currencySell="RUB",
            amountSell=30_000,
            currencyBuy="THB",
            amountBuy=12_000,
            rate=0.4,
            methodGet="qrcode",
        ),
    )

    assert created.rate == pytest.approx(0.5)
    assert created.amountBuy == pytest.approx(15_000)
    assert created.deliveryRate is None


@pytest.mark.asyncio
async def test_cash_rate_error_does_not_create_partial_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отсутствующая USDT-пара должна остановить flow до сохранения Order."""
    city = City(name="Bangkok-no-conversion", country=Country.THAILAND)
    customer = User(telegram_id=700100, username="customer-no-conversion")
    rate = Rate(currency="RUBTHB", price=0.4, margin=0.0, country=Country.THAILAND)
    db_session.add_all([city, customer, rate])
    await db_session.flush()
    customer.city_id = city.id
    await db_session.commit()
    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())

    with pytest.raises(AntExException) as error:
        await order_flow.create_order_for_user(
            db_session,
            customer,
            MiniappOrderCreate(
                country=Country.THAILAND,
                cityId=city.id,
                currencySell="RUB",
                amountSell=30_000,
                currencyBuy="THB",
                amountBuy=12_000,
                rate=0.4,
                methodGet="cash",
            ),
        )

    assert error.value.code == "RATE_UNAVAILABLE"
    assert await db_session.scalar(select(Order)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial_access", "user_delivery", "expected_access"),
    [
        (False, DeliveryOutcome.SENT, True),
        (True, DeliveryOutcome.INACCESSIBLE, False),
    ],
)
async def test_create_order_syncs_write_access_from_actual_user_delivery(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    initial_access: bool,
    user_delivery: DeliveryOutcome,
    expected_access: bool,
) -> None:
    """Ловит рассинхронизацию кэша после успешной или постоянно неуспешной доставки."""
    city = City(name="Bangkok", country=Country.THAILAND)
    manager = User(
        telegram_id=710001,
        username="manager-sync",
        role=int(UserRole.MANAGER),
    )
    customer = User(
        telegram_id=710002,
        username="customer-sync",
        telegram_write_access=initial_access,
    )
    rate = Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND)
    db_session.add_all([city, manager, customer, rate, _usdt_thb_rate()])
    await db_session.flush()
    customer.city_id = city.id
    await db_session.commit()

    async def notify(order, user, assigned_manager, *, notify_user=True):
        return OrderCreatedDelivery(user=user_delivery, manager=DeliveryOutcome.RICH)

    monkeypatch.setattr(order_flow, "notify_order_created", notify)
    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        cityId=city.id,
        currencySell="RUB",
        amountSell=30000,
        currencyBuy="THB",
        amountBuy=12000,
        rate=0.4,
        methodGet="cash",
    )

    await order_flow.create_order_for_user(db_session, customer, payload)

    await db_session.refresh(customer)
    assert customer.telegram_write_access is expected_access


@pytest.mark.asyncio
async def test_create_order_persists_customer_notification_message_id(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    city = City(name="Bangkok", country=Country.THAILAND)
    manager = User(
        telegram_id=700001,
        username="manager",
        first_name="Order",
        role=int(UserRole.MANAGER),
    )
    customer = User(telegram_id=700002, username="customer", first_name="Happy")
    rate = Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND)
    db_session.add_all([city, manager, customer, rate, _usdt_thb_rate()])
    await db_session.flush()
    customer.city_id = city.id
    await db_session.commit()

    async def notify(order, user, assigned_manager, *, notify_user=True):
        assert user is customer
        assert assigned_manager is manager
        assert notify_user is True
        order.userNotificationMessageId = 89
        return OrderCreatedDelivery(user=DeliveryOutcome.SENT, manager=DeliveryOutcome.RICH)

    monkeypatch.setattr(order_flow, "notify_order_created", notify)
    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        cityId=city.id,
        currencySell="RUB",
        amountSell=30000,
        currencyBuy="THB",
        amountBuy=12000,
        rate=0.4,
        methodGet="cash",
    )

    created = await order_flow.create_order_for_user(db_session, customer, payload)
    order_id = created.id
    await db_session.rollback()
    stored = await db_session.get(Order, order_id)

    assert stored is not None
    assert stored.userNotificationMessageId == 89


@pytest.mark.asyncio
async def test_create_order_returns_reloaded_order_when_notification_id_commit_fails(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    city = City(name="Bangkok", country=Country.THAILAND)
    manager = User(telegram_id=700001, username="manager", role=int(UserRole.MANAGER))
    customer = User(telegram_id=700002, username="customer", first_name="Happy")
    rate = Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND)
    db_session.add_all([city, manager, customer, rate, _usdt_thb_rate()])
    await db_session.flush()
    customer.city_id = city.id
    await db_session.commit()

    async def notify(order, user, assigned_manager, *, notify_user=True):
        order.userNotificationMessageId = 89
        return OrderCreatedDelivery(user=DeliveryOutcome.SENT, manager=DeliveryOutcome.RICH)

    original_commit = db_session.commit
    commit_count = 0

    async def fail_secondary_commit() -> None:
        nonlocal commit_count
        commit_count += 1
        if commit_count == 2:
            raise SQLAlchemyError("tracking write unavailable")
        await original_commit()

    monkeypatch.setattr(order_flow, "notify_order_created", notify)
    monkeypatch.setattr(db_session, "commit", fail_secondary_commit)
    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        cityId=city.id,
        currencySell="RUB",
        amountSell=30000,
        currencyBuy="THB",
        amountBuy=12000,
        rate=0.4,
        methodGet="cash",
    )

    created = await order_flow.create_order_for_user(db_session, customer, payload)

    assert created.publicNumber
    assert created.user.username == "customer"
    assert created.city.name == "Bangkok"


@pytest.mark.asyncio
async def test_create_order_snapshots_latest_marketing_touch_and_window(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    city = City(name="Phuket", country=Country.THAILAND)
    customer = User(telegram_id=700020, username="snapshot", first_name="Snapshot")
    rate = Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND)
    platform = MarketingPlatform(slug="snapshot_ads", name="Snapshot Ads")
    currency = MarketingCurrency(code="TST", name="Test")
    db_session.add_all([city, customer, rate, platform, currency, _usdt_thb_rate()])
    await db_session.flush()
    campaign = MarketingCampaign(
        code="SNAPSHOT01",
        name="Snapshot",
        platform_id=platform.id,
        currency_id=currency.id,
        status="active",
    )
    db_session.add(campaign)
    await db_session.flush()
    touch = MarketingTouch(
        user_id=customer.id,
        campaign_id=campaign.id,
        user_state="returning",
        touched_at=datetime.now(UTC),
    )
    db_session.add(touch)
    await db_session.flush()
    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())
    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        cityId=city.id,
        currencySell="RUB",
        amountSell=30_000,
        currencyBuy="THB",
        amountBuy=12_000,
        rate=0.4,
        methodGet="cash",
    )

    order = await order_flow.create_order_for_user(db_session, customer, payload)

    snapshot = await db_session.scalar(
        select(OrderAttribution).where(OrderAttribution.order_id == order.id)
    )
    assert snapshot is not None
    assert snapshot.marketing_touch_id == touch.id
    assert snapshot.campaign_id == campaign.id
    assert snapshot.attribution_type == "reengagement"
    assert snapshot.lookback_days == 7

    config = await ConfigRepository(db_session).get_or_create()
    config.marketing_attribution_window_days = 14
    await db_session.commit()
    await db_session.refresh(snapshot)
    assert snapshot.lookback_days == 7


@pytest.mark.asyncio
async def test_create_order_for_user_allows_missing_contact_and_keeps_order_contact_empty(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    rate = Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND)

    db_session.add_all([city, manager, customer, rate])
    await db_session.flush()

    customer.city_id = city.id
    await db_session.commit()

    monkeypatch.setattr(order_flow, "notify_order_created", AsyncMock())

    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        currencySell="RUB",
        amountSell=20000,
        currencyBuy="THB",
        amountBuy=8000,
        rate=0.4,
        methodGet="qrcode",
    )

    created_order = await order_flow.create_order_for_user(db_session, customer, payload)

    assert created_order.contactTelegram is None


@pytest.mark.asyncio
async def test_create_order_for_user_keeps_saved_order_when_notification_fails(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
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
    rate = Rate(currency="RUBTHB", price=0.41, margin=3.0, country=Country.THAILAND)

    db_session.add_all([city, manager, customer, rate])
    await db_session.flush()
    manager.city_id = city.id
    customer.city_id = city.id
    await db_session.commit()

    notify_mock = AsyncMock(side_effect=RuntimeError("telegram unavailable"))
    monkeypatch.setattr(order_flow, "notify_order_created", notify_mock)

    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        currencySell="RUB",
        amountSell=20000,
        currencyBuy="THB",
        amountBuy=8000,
        rate=0.4,
        methodGet="qrcode",
    )

    with caplog.at_level(logging.ERROR, logger="app.services.order_flow"):
        created_order = await order_flow.create_order_for_user(db_session, customer, payload)

    notify_mock.assert_awaited_once()
    stored_order = await db_session.scalar(select(Order).where(Order.id == created_order.id))
    assert stored_order is not None
    assert stored_order.publicNumber == created_order.publicNumber
    assert "Failed to send order created notifications" in caplog.text


@pytest.mark.asyncio
async def test_min_amount_rejects_below_limit_cash_rub() -> None:
    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        currencySell="RUB",
        amountSell=10_000,
        currencyBuy="THB",
        amountBuy=4000,
        rate=0.4,
        methodGet="cash",
    )

    with pytest.raises(AntExException) as exc_info:
        order_flow._validate_min_amount(payload)

    assert exc_info.value.code == "MIN_AMOUNT"
    assert exc_info.value.status_code == 422
    assert exc_info.value.params["minAmount"] == 25_000


@pytest.mark.asyncio
async def test_min_amount_rejects_below_limit_qrcode_usdt() -> None:
    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        currencySell="USDT",
        amountSell=100,
        currencyBuy="THB",
        amountBuy=3500,
        rate=35.0,
        methodGet="qrcode",
    )

    with pytest.raises(AntExException) as exc_info:
        order_flow._validate_min_amount(payload)

    assert exc_info.value.code == "MIN_AMOUNT"
    assert exc_info.value.params["minAmount"] == 300


@pytest.mark.asyncio
async def test_min_amount_allows_at_limit() -> None:
    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        currencySell="RUB",
        amountSell=25_000,
        currencyBuy="THB",
        amountBuy=10_000,
        rate=0.4,
        methodGet="cash",
    )

    order_flow._validate_min_amount(payload)


@pytest.mark.asyncio
async def test_min_amount_allows_above_limit() -> None:
    payload = MiniappOrderCreate(
        country=Country.THAILAND,
        currencySell="USDT",
        amountSell=500,
        currencyBuy="THB",
        amountBuy=17_500,
        rate=35.0,
        methodGet="bank_account",
    )

    order_flow._validate_min_amount(payload)


def test_get_min_amount_uses_method_and_currency_limits() -> None:
    assert order_flow.get_min_amount("qrcode", "rub") == 15_000
    assert order_flow.get_min_amount("cash", "USDT") == 500
    assert order_flow.get_min_amount("unknown", "RUB") is None
