from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.routers.admin import get_today_start_for_timezone
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.order import OrderStatus
from app.enums.user import UserRole
from app.exceptions import AntExException
from app.models.admin import Admin
from app.models.aex import AexLedgerEntry, AexPersonalRate, AexWallet
from app.models.attribution import MarketingTouch, UserAcquisition
from app.models.city import City
from app.models.config import Config
from app.models.marketing import MarketingCampaign, MarketingCurrency, MarketingPlatform
from app.models.order import Order
from app.models.rate import Rate
from app.models.user import User


def _strip_bidi_marks(text: str) -> str:
    return text.replace("\u2068", "").replace("\u2069", "")


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
        photo_url="https://t.me/i/userpic/320/customer.jpg",
        role=int(UserRole.USER),
    )
    db_session.add_all(
        [
            city,
            manager,
            customer,
            Rate(
                currency="RUBTHB",
                price=0.41,
                margin=3.0,
                country=Country.THAILAND,
                display_reversed=True,
            ),
            Rate(
                currency="RUBGEL",
                price=0.03,
                margin=3.0,
                country=Country.GEORGIA,
                display_reversed=True,
            ),
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


async def credit_aex_wallet(
    db_session: AsyncSession,
    user_id: int,
    amount: int,
) -> AexWallet:
    wallet = AexWallet(user_id=user_id, balance_available=amount, balance_reserved=0)
    db_session.add(wallet)
    await db_session.flush()
    return wallet


async def get_latest_order_for_user(db_session: AsyncSession, user_id: int) -> Order:
    """Вернуть последнюю созданную заявку пользователя для проверки POST без response DTO."""
    order = await db_session.scalar(
        select(Order).where(Order.UserId == user_id).order_by(Order.id.desc())
    )
    assert order is not None
    return order


@pytest.mark.asyncio
async def test_miniapp_home_and_exchange_are_backend_driven(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    db_session.add(Rate(currency="USDTRUB", price=80.0, margin=5.0, country=None, is_internal=True))
    await db_session.flush()
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
    assert home["profile"]["photoUrl"] == "https://t.me/i/userpic/320/customer.jpg"
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
    assert home["locations"][0]["countryFlag"] == "🇹🇭"
    assert home["locations"][0]["id"] == str(city.id)
    assert home["rates"]["featured"][0]["country"] == "thailand"
    assert home["rates"]["featured"][0]["countryFlag"] == "🇹🇭"
    assert home["rates"]["featured"][0]["fromCurrency"] == "RUB"
    assert home["rates"]["featured"][0]["toCurrency"] == "THB"
    assert home["rates"]["featured"][0]["rate"] == pytest.approx(2.51)
    assert home["rates"]["featured"][0]["calculationRate"] == pytest.approx(0.3977)
    assert home["rates"]["featured"][0]["rateDisplay"] == "2.51"
    assert home["rates"]["featured"][0]["amountSellExample"] == 5000
    expected_methods = ["qrcode", "cash", "bank_account", "pay_services"]
    assert home["rates"]["featured"][0]["availableMethods"] == expected_methods
    assert home["rates"]["featured"][1]["availableMethods"] == expected_methods
    assert [service["id"] for service in home["services"]] == [
        "cash",
        "qrcode",
        "bank_account",
        "pay_services",
    ]

    assert exchange_response.status_code == 200
    exchange = exchange_response.json()
    assert exchange["calculator"] == {
        "fromCurrency": "RUB",
        "toCurrency": "THB",
        "amountSell": 5000,
    }
    assert exchange["quote"]["rate"] == pytest.approx(0.3977)
    assert exchange["quote"]["rateDisplay"] == "2.51"
    assert exchange["quote"]["rateText"] == "1 THB = 2.51 RUB"
    assert exchange["quote"]["amountBuy"] == pytest.approx(1988.5)
    assert exchange["pairs"][0]["id"] == "rub-thb"
    assert exchange["pairs"][0]["fromCurrency"] == "RUB"
    assert exchange["pairs"][0]["toCurrency"] == "THB"
    assert exchange["pairs"][0]["rate"] == pytest.approx(2.51)
    assert exchange["pairs"][0]["calculationRate"] == pytest.approx(0.3977)
    assert exchange["pairs"][0]["rateDisplay"] == "2.51"
    assert exchange["pairs"][0]["rateText"] == "1 THB = 2.51 RUB"
    assert exchange["aexPayoutOptions"] == [
        {
            "currencyBuy": "USDT",
            "rate": 1.0,
            "rateDisplay": "1.00",
            "rateText": "1 ATXG = 1.00 USDT",
            "availableMethods": ["bank_account"],
        },
        {
            "currencyBuy": "RUB",
            "rate": 76.0,
            "rateDisplay": "76.00",
            "rateText": "1 ATXG = 76.00 RUB",
            "availableMethods": ["bank_account"],
        },
    ]
    assert {"rub-gel", "rub-vnd", "usdt-gel", "usdt-vnd"} <= {
        pair["id"] for pair in exchange["pairs"]
    }
    availability = exchange["managerAvailability"]
    assert availability["status"] in {"working", "offline"}
    assert availability["scheduleEnabled"] is True
    assert availability["workingDaysUtc"] == [1, 2, 3, 4, 5, 6, 7]
    assert availability["startTimeUtc"] == "06:00"
    assert availability["endTimeUtc"] == "18:00"
    assert availability["businessHoursText"] == "Ежедневно с 09:00 до 21:00 МСК"  # noqa: RUF001


@pytest.mark.asyncio
async def test_miniapp_manager_availability_is_available_without_exchange_screen(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Мини-приложение получает режим менеджеров без полной exchange-котировки."""
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.get(
        "/api/miniapp/manager-availability",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "status",
        "scheduleEnabled",
        "workingDaysUtc",
        "startTimeUtc",
        "endTimeUtc",
        "currentStartAt",
        "currentEndAt",
        "nextStartAt",
        "businessHoursText",
    }
    assert response.json()["status"] in {"working", "offline"}


@pytest.mark.asyncio
async def test_miniapp_exchange_omits_rub_payout_without_internal_rate(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """RUB не предлагается, когда системный USDTRUB ещё не получен."""
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.get(
        "/api/miniapp/exchange",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert [item["currencyBuy"] for item in response.json()["aexPayoutOptions"]] == ["USDT"]
    assert "USDTRUB" not in response.text


@pytest.mark.asyncio
async def test_miniapp_aex_referral_returns_ready_link(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    referred = User(
        telegram_id=700003,
        username="invited",
        first_name="Invited",
    )
    db_session.add(referred)
    await db_session.flush()
    db_session.add(
        UserAcquisition(user_id=referred.id, source_type="referral", referrer_user_id=customer.id)
    )
    await db_session.flush()
    order = Order(
        UserId=referred.id,
        CityId=None,
        country=Country.THAILAND,
        currencySell="RUB",
        amountSell=1000,
        currencyBuy="THB",
        amountBuy=400,
        rate=0.4,
        status=int(OrderStatus.COMPLETED),
        contactTelegram="@invited",
        methodGet="qrcode",
        publicNumber="RF0001",
    )
    wallet = AexWallet(user_id=customer.id)
    db_session.add_all([order, wallet])
    await db_session.flush()
    db_session.add(
        AexLedgerEntry(
            wallet_id=wallet.id,
            amount=12.5,
            entry_type="credit",
            reference_type="referral",
            reference_id=str(order.id),
            description="Referral bonus for order",
        )
    )
    await db_session.flush()
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    monkeypatch.setattr(settings, "telegram_bot_username", "antex_test_bot")

    response = await client.get(
        "/api/miniapp/aex/referral",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["referralCode"]) == 8
    assert (
        data["referralLink"] == f"https://t.me/antex_test_bot?startapp=ref_{data['referralCode']}"
    )
    assert data["totalReferrals"] == 1
    assert data["programConfig"] == {
        "referralPercent": "0.2",
        "referralMinWithdraw": "100",
        "referralMaxWithdraw": None,
        "aexRate": "1",
        "aexWithdrawLimit": "100",
    }
    assert "referrals" not in data


@pytest.mark.asyncio
async def test_miniapp_aex_referrals_returns_paginated_safe_list(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    first = User(
        telegram_id=700011,
        username="first_ref",
        first_name="First",
        last_name="Referral",
        phone="+79990000001",
        photo_url="https://t.me/i/userpic/320/first.jpg",
    )
    second = User(
        telegram_id=700012,
        username=None,
        first_name="Second",
        last_name=None,
        phone="+79990000002",
    )
    other_referrer = User(telegram_id=700013, username="other_referrer")
    db_session.add_all([first, second, other_referrer])
    await db_session.flush()
    unrelated = User(
        telegram_id=700014,
        username="unrelated_ref",
        first_name="Other",
    )
    wallet = AexWallet(user_id=customer.id)
    db_session.add_all([unrelated, wallet])
    await db_session.flush()
    db_session.add_all(
        [
            UserAcquisition(user_id=first.id, source_type="referral", referrer_user_id=customer.id),
            UserAcquisition(
                user_id=second.id, source_type="referral", referrer_user_id=customer.id
            ),
            UserAcquisition(
                user_id=unrelated.id, source_type="referral", referrer_user_id=other_referrer.id
            ),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            AexPersonalRate(user_id=customer.id, rate=Decimal("0.015")),
            AexLedgerEntry(
                wallet_id=wallet.id,
                amount=Decimal("12.50"),
                entry_type="credit",
                reference_type="referral",
                reference_id="101",
                description="Referral bonus",
            ),
            AexLedgerEntry(
                wallet_id=wallet.id,
                amount=Decimal("2.25"),
                entry_type="credit",
                reference_type="referral",
                reference_id="102",
                description="Referral bonus",
            ),
            AexLedgerEntry(
                wallet_id=wallet.id,
                amount=Decimal("-1.00"),
                entry_type="debit",
                reference_type="transfer",
                reference_id="103",
                description="Withdraw",
            ),
        ]
    )
    await db_session.flush()
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.get(
        "/api/miniapp/aex/referrals?limit=1&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert data["total"] == 2
    assert data["hasMore"] is True
    assert data["totalAccrued"] == "14.75"
    assert data["rewardPercent"] == "1.5"
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == first.id
    assert item["displayName"] == "First Referral"
    assert item["username"] == "first_ref"
    assert item["photoUrl"] == "https://t.me/i/userpic/320/first.jpg"
    assert item["rewardPercent"] == "1.5"
    assert item["joinedAt"] is not None
    assert "phone" not in item
    assert "telegram_id" not in item
    assert "telegramId" not in item
    assert "earnedAex" not in item
    assert "totalEarned" not in item
    assert unrelated.id not in {referral["id"] for referral in data["items"]}


@pytest.mark.asyncio
async def test_admin_config_updates_referral_program_settings_for_miniapp(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all([admin, Config(id=1, enabled=True)])
    await db_session.flush()
    admin_token = create_access_token({"sub": str(admin.id), "type": "admin"})
    user_token = create_access_token({"sub": str(customer.id), "role": customer.role})

    patch_response = await client.patch(
        "/api/admin/config",
        json={
            "referralPercent": "0.35",
            "referralMinWithdraw": "250",
            "referralMaxWithdraw": "5000",
            "aexRate": "1.2",
            "aexWithdrawLimit": "750",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    referral_response = await client.get(
        "/api/miniapp/aex/referral",
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["referralPercent"] == "0.35"
    assert patch_response.json()["referralMinWithdraw"] == "250"
    assert patch_response.json()["referralMaxWithdraw"] == "5000"
    assert patch_response.json()["aexRate"] == "1.2"
    assert patch_response.json()["aexWithdrawLimit"] == "750"
    assert referral_response.status_code == 200
    assert referral_response.json()["programConfig"] == {
        "referralPercent": "0.35",
        "referralMinWithdraw": "250",
        "referralMaxWithdraw": "5000",
        "aexRate": "1.2",
        "aexWithdrawLimit": "750",
    }


@pytest.mark.asyncio
async def test_admin_manager_schedule_is_reflected_in_miniapp_profile_and_exchange(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Проверяет единый config-источник режима без перезапуска backend."""
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all([admin, Config(id=1, enabled=True)])
    await db_session.flush()
    admin_token = create_access_token({"sub": str(admin.id), "type": "admin"})
    user_token = create_access_token({"sub": str(customer.id), "role": customer.role})
    headers = {"Authorization": f"Bearer {user_token}"}

    patch_response = await client.patch(
        "/api/admin/config",
        json={
            "managerScheduleEnabled": False,
            "managerWorkingDaysUtc": [1, 2, 3, 4, 5],
            "managerStartTimeUtc": "07:00",
            "managerEndTimeUtc": "19:00",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    profile_response = await client.get("/api/miniapp/profile", headers=headers)
    exchange_response = await client.get("/api/miniapp/exchange", headers=headers)

    assert patch_response.status_code == 200
    assert patch_response.json()["managerWorkingDaysUtc"] == [1, 2, 3, 4, 5]
    assert patch_response.json()["managerStartTimeUtc"] == "07:00"
    assert patch_response.json()["managerEndTimeUtc"] == "19:00"
    assert profile_response.json()["managerAvailability"]["status"] == "unknown"
    assert exchange_response.json()["managerAvailability"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_admin_manager_schedule_rejects_offset_bearing_utc_times(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all([admin, Config(id=1, enabled=True)])
    await db_session.flush()
    admin_token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.patch(
        "/api/admin/config",
        json={"managerStartTimeUtc": "06:00+03:00"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_manager_schedule_rejects_second_precision_times(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all([admin, Config(id=1, enabled=True)])
    await db_session.flush()
    admin_token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.patch(
        "/api/admin/config",
        json={"managerStartTimeUtc": "06:00:30"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_config_rejects_negative_aex_withdraw_limit(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all([admin, Config(id=1, enabled=True)])
    await db_session.flush()
    admin_token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.patch(
        "/api/admin/config",
        json={"aexWithdrawLimit": "-1"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_config_rejects_non_numeric_or_duplicate_manager_working_days(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Не допускает неявное приведение внешних данных расписания в UTC-дни."""  # noqa: RUF002
    client, db_session = api_client
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all([admin, Config(id=1, enabled=True)])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    string_day_response = await client.patch(
        "/api/admin/config",
        json={"managerWorkingDaysUtc": ["1"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    duplicate_days_response = await client.patch(
        "/api/admin/config",
        json={"managerWorkingDaysUtc": [1, 1]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert string_day_response.status_code == 422
    assert duplicate_days_response.status_code == 422


@pytest.mark.asyncio
async def test_admin_config_allows_empty_manager_days_only_when_schedule_disabled(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all([admin, Config(id=1, enabled=True)])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    enabled_response = await client.patch(
        "/api/admin/config",
        json={"managerScheduleEnabled": True, "managerWorkingDaysUtc": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    disabled_response = await client.patch(
        "/api/admin/config",
        json={"managerScheduleEnabled": False, "managerWorkingDaysUtc": []},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert enabled_response.status_code == 422
    assert disabled_response.status_code == 200
    assert disabled_response.json()["managerScheduleEnabled"] is False
    assert disabled_response.json()["managerWorkingDaysUtc"] == []


@pytest.mark.asyncio
async def test_admin_config_rejects_empty_manager_days_when_existing_schedule_enabled(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all([admin, Config(id=1, enabled=True, manager_schedule_enabled=True)])
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.patch(
        "/api/admin/config",
        json={"managerWorkingDaysUtc": []},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_config_rejects_enabling_manager_schedule_with_existing_empty_days(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    admin = Admin(username="admin", password_hash="unused")
    db_session.add_all(
        [
            admin,
            Config(
                id=1,
                enabled=True,
                manager_schedule_enabled=False,
                manager_working_days_utc=[],
            ),
        ]
    )
    await db_session.flush()
    token = create_access_token({"sub": str(admin.id), "type": "admin"})

    response = await client.patch(
        "/api/admin/config",
        json={"managerScheduleEnabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_miniapp_aex_transactions_returns_offset_pagination_contract(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    wallet = AexWallet(user_id=customer.id)
    db_session.add(wallet)
    await db_session.flush()
    db_session.add_all(
        [
            AexLedgerEntry(
                wallet_id=wallet.id,
                amount=12.5,
                entry_type="credit",
                reference_type="referral",
                reference_id="1",
                description="Referral reward",
            ),
            AexLedgerEntry(
                wallet_id=wallet.id,
                amount=-5,
                entry_type="debit",
                reference_type="transfer",
                reference_id="2",
                description="Withdrawal",
            ),
        ]
    )
    await db_session.commit()
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.get(
        "/api/miniapp/aex/transactions",
        params={"limit": 1, "offset": 0},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert data["total"] == 2
    assert data["hasMore"] is True
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_miniapp_aex_transactions_describes_referral_reward_by_public_order_number(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    referred = User(
        telegram_id=700004,
        username="referred",
        first_name="Referred",
    )
    wallet = AexWallet(user_id=customer.id)
    db_session.add_all([referred, wallet])
    await db_session.flush()
    db_session.add(
        UserAcquisition(user_id=referred.id, source_type="referral", referrer_user_id=customer.id)
    )
    await db_session.flush()
    order = Order(
        UserId=referred.id,
        CityId=None,
        country=Country.THAILAND,
        currencySell="RUB",
        amountSell=10000,
        currencyBuy="THB",
        amountBuy=4000,
        rate=0.4,
        status=int(OrderStatus.COMPLETED),
        contactTelegram="@referred",
        methodGet="qrcode",
        publicNumber="2026060001",
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add(
        AexLedgerEntry(
            wallet_id=wallet.id,
            amount=100,
            entry_type="credit",
            reference_type="referral",
            reference_id=str(order.id),
            description=f"Referral bonus for order #{order.id}",
            createdAt=datetime(2026, 6, 22, 15, 37, tzinfo=UTC),
        )
    )
    await db_session.commit()
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.get(
        "/api/miniapp/aex/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["type"] == "referral_reward"
    assert _strip_bidi_marks(item["description"]) == "Реферальное начисление по заявке 2026060001"
    assert f"#{order.id}" not in item["description"]


@pytest.mark.asyncio
async def test_miniapp_aex_transactions_maps_withdraw_lifecycle(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    wallet = AexWallet(user_id=customer.id)
    db_session.add(wallet)
    await db_session.flush()
    order = Order(
        UserId=customer.id,
        CityId=None,
        country=Country.THAILAND,
        currencySell="ATXG",
        amountSell=200,
        currencyBuy="THB",
        amountBuy=7240,
        rate=36.2,
        status=int(OrderStatus.COMPLETED),
        contactTelegram="@customer",
        methodGet="qrcode",
        publicNumber="2026070007",
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add_all(
        [
            AexLedgerEntry(
                wallet_id=wallet.id,
                amount=100,
                entry_type="credit",
                reference_type="referral",
                reference_id=None,
                description="Referral reward",
                createdAt=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
            ),
            AexLedgerEntry(
                wallet_id=wallet.id,
                amount=50,
                entry_type="hold",
                reference_type="order_withdraw_hold",
                reference_id=str(order.id),
                description="Reserved for withdrawal",
                createdAt=datetime(2026, 7, 1, 11, 0, tzinfo=UTC),
            ),
            AexLedgerEntry(
                wallet_id=wallet.id,
                amount=-30,
                entry_type="debit",
                reference_type="order_withdraw_debit",
                reference_id=str(order.id),
                description="Debited for withdrawal",
                createdAt=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
            ),
            AexLedgerEntry(
                wallet_id=wallet.id,
                amount=20,
                entry_type="release",
                reference_type="order_withdraw_release",
                reference_id=str(order.id),
                description="Released withdrawal reserve",
                createdAt=datetime(2026, 7, 1, 13, 0, tzinfo=UTC),
            ),
        ]
    )
    await db_session.commit()
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.get(
        "/api/miniapp/aex/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [(item["type"], item["balanceAfter"]) for item in items] == [
        ("refund", 70),
        ("debited", 70),
        ("reserved", 100),
        ("referral_reward", 100),
    ]
    assert [_strip_bidi_marks(item["description"]) for item in items] == [
        "Возврат по заявке 2026070007",
        "Списано по заявке 2026070007",
        "Зарезервировано по заявке 2026070007",
        "Реферальное начисление",
    ]


@pytest.mark.asyncio
async def test_miniapp_aex_transactions_respect_english_locale(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    customer.language_code_app = "en"
    wallet = AexWallet(user_id=customer.id)
    db_session.add(wallet)
    await db_session.flush()
    order = Order(
        UserId=customer.id,
        CityId=None,
        country=Country.THAILAND,
        currencySell="RUB",
        amountSell=10000,
        currencyBuy="THB",
        amountBuy=4000,
        rate=0.4,
        status=int(OrderStatus.COMPLETED),
        contactTelegram="@customer",
        methodGet="qrcode",
        publicNumber="2026070008",
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add(
        AexLedgerEntry(
            wallet_id=wallet.id,
            amount=25,
            entry_type="hold",
            reference_type="order_withdraw_hold",
            reference_id=str(order.id),
            description="Reserved for withdrawal",
            createdAt=datetime(2026, 7, 1, 11, 0, tzinfo=UTC),
        )
    )
    await db_session.commit()
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.get(
        "/api/miniapp/aex/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["type"] == "reserved"
    assert _strip_bidi_marks(item["description"]) == "Reserved for order 2026070008"


@pytest.mark.asyncio
async def test_miniapp_referral_apply_binds_once(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    referrer_one = User(telegram_id=700004, username="ref_one", referral_code="A7kP2mX9")
    referrer_two = User(telegram_id=700005, username="ref_two", referral_code="hF84LmQz")
    db_session.add_all([referrer_one, referrer_two])
    await db_session.flush()
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    first = await client.post(
        "/api/miniapp/aex/referral/apply",
        json={"code": "A7kP2mX9"},
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await client.post(
        "/api/miniapp/aex/referral/apply",
        json={"code": "hF84LmQz"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first.status_code == 200
    assert first.json() == {"success": True}
    assert second.status_code == 409
    await db_session.refresh(customer)
    ua = (
        await db_session.execute(
            select(UserAcquisition).where(UserAcquisition.user_id == customer.id)
        )
    ).scalar_one_or_none()
    assert ua is not None
    assert ua.referrer_user_id == referrer_one.id


@pytest.mark.asyncio
async def test_miniapp_referral_apply_invalid_or_missing_code_returns_expected_message(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    invalid_format = await client.post(
        "/api/miniapp/aex/referral/apply",
        json={"code": "bad-code"},
        headers={"Authorization": f"Bearer {token}"},
    )
    missing = await client.post(
        "/api/miniapp/aex/referral/apply",
        json={"code": "N2vX8aBc"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert invalid_format.status_code == 422
    assert missing.status_code == 422
    assert invalid_format.json()["message"] == "Неверный реферальный код. Проверте или удалите!"
    assert missing.json()["message"] == "Неверный реферальный код. Проверте или удалите!"


@pytest.mark.asyncio
async def test_miniapp_readonly_dev_request_without_token_uses_existing_env_dev_user(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)

    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "dev_user_id", customer.telegram_id)

    response = await client.get("/api/miniapp/home")

    assert response.status_code == 200
    assert response.json()["profile"]["id"] == customer.id
    assert response.json()["profile"]["username"] == customer.username
    assert response.json()["profile"]["displayName"] == "Happy"

    users_count = await db_session.scalar(select(func.count(User.id)))
    assert users_count == 2


@pytest.mark.asyncio
async def test_miniapp_readonly_dev_request_without_db_user_is_rejected(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    await seed_exchange_data(db_session)

    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "dev_user_id", 333366854)

    response = await client.get("/api/miniapp/home")

    assert response.status_code == 401

    users_count = await db_session.scalar(select(func.count(User.id)))
    assert users_count == 2


@pytest.mark.asyncio
async def test_miniapp_stateful_request_without_token_uses_dev_user_from_db(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)

    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "dev_user_id", customer.telegram_id)

    response = await client.get("/api/miniapp/orders")

    assert response.status_code == 200
    assert response.json() == {"items": [], "limit": 10, "offset": 0, "total": 0, "hasMore": False}

    users_count = await db_session.scalar(select(func.count(User.id)))
    assert users_count == 2


@pytest.mark.asyncio
async def test_miniapp_profile_support_points_to_manager_chat(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    _, _manager, customer = await seed_exchange_data(db_session)
    monkeypatch.setattr(settings, "telegram_bot_username", "antex_test_bot")
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.get(
        "/api/miniapp/profile",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    profile = response.json()
    assert profile["user"]["photoUrl"] == "https://t.me/i/userpic/320/customer.jpg"
    support = next(item for item in profile["menu"] if item["id"] == "support")
    assert support["action"] == "link"
    assert support["href"] == "https://t.me/antex_test_bot"


@pytest.mark.asyncio
async def test_miniapp_orders_support_limit_offset_pagination(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    orders = [
        Order(
            UserId=customer.id,
            CityId=city.id,
            country=Country.THAILAND,
            currencySell="RUB",
            amountSell=5000 + index,
            currencyBuy="THB",
            amountBuy=2000 + index,
            rate=0.4,
            status=int(OrderStatus.CREATED),
            methodGet="cash",
            publicNumber=f"202605{index:04d}",
            createdAt=datetime(2026, 5, index, 12, 0, tzinfo=UTC),
        )
        for index in range(1, 8)
    ]
    db_session.add_all(orders)
    await db_session.flush()

    first_response = await client.get(
        "/api/miniapp/orders?limit=5&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    second_response = await client.get(
        "/api/miniapp/orders?limit=5&offset=5",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first_response.status_code == 200
    first_page = first_response.json()
    assert first_page["limit"] == 5
    assert first_page["offset"] == 0
    assert first_page["total"] == 7
    assert first_page["hasMore"] is True
    assert [item["publicNumber"] for item in first_page["items"]] == [
        "2026050007",
        "2026050006",
        "2026050005",
        "2026050004",
        "2026050003",
    ]

    assert second_response.status_code == 200
    second_page = second_response.json()
    assert second_page["limit"] == 5
    assert second_page["offset"] == 5
    assert second_page["total"] == 7
    assert second_page["hasMore"] is False
    assert [item["publicNumber"] for item in second_page["items"]] == [
        "2026050002",
        "2026050001",
    ]


@pytest.mark.asyncio
async def test_miniapp_request_without_token_is_rejected_in_production(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    await seed_exchange_data(db_session)

    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "dev_user_id", 333366854)

    response = await client.get("/api/miniapp/rates")

    assert response.status_code == 401

    users_count = await db_session.scalar(select(func.count(User.id)))
    assert users_count == 2


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
    assert direct_response.json()["rate"] == pytest.approx(0.3977)
    assert direct_response.json()["rateDisplay"] == "2.51"
    assert direct_response.json()["rateText"] == "1 THB = 2.51 RUB"
    assert direct_response.json()["amountBuy"] == pytest.approx(3977)

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
    assert rub_gel_response.json()["rate"] == pytest.approx(0.0291)
    assert rub_gel_response.json()["rateDisplay"] == "34.36"
    assert rub_gel_response.json()["rateText"] == "1 GEL = 34.36 RUB"
    assert rub_gel_response.json()["amountBuy"] == pytest.approx(291)
    expected_methods = ["qrcode", "cash", "bank_account", "pay_services"]
    assert rub_gel_response.json()["availableMethods"] == expected_methods

    assert usdt_vnd_response.status_code == 200
    assert usdt_vnd_response.json()["rate"] == 24735.0
    assert usdt_vnd_response.json()["rateDisplay"] == "24735.00"
    assert usdt_vnd_response.json()["rateText"] == "1 USDT = 24735.00 VND"
    assert usdt_vnd_response.json()["amountBuy"] == pytest.approx(2 * 24735.0)
    assert usdt_vnd_response.json()["availableMethods"] == expected_methods

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
async def test_miniapp_cash_order_returns_empty_created_response(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Создание cash-заявки подтверждается пустым 201 без ORM-сериализации города."""
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "cityId": city.id,
            "currencySell": "rub",
            "amountSell": 25000,
            "currencyBuy": "thb",
            "amountBuy": 123.45,
            "rate": 9.99,
            "methodGet": "cash",
        },
    )

    assert response.status_code == 201
    assert response.content == b""

    history_response = await client.get(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert history_response.status_code == 200
    history_item = history_response.json()["items"][0]
    assert history_item["amountBuy"] == pytest.approx(9_590.5)
    assert history_item["rate"] == pytest.approx(0.38362)
    assert history_item["rateDisplay"] == "2.61"


@pytest.mark.asyncio
async def test_miniapp_order_is_created_with_server_quote_and_display_snapshot(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    from app.services import order_flow

    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "rub",
            "amountSell": 20000,
            "currencyBuy": "thb",
            "amountBuy": 123.45,
            "rate": 9.99,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 201
    assert response.content == b""
    order = await get_latest_order_for_user(db_session, customer.id)
    assert order.CityId is None
    assert order.country is Country.THAILAND
    assert order.currencySell == "RUB"
    assert order.currencyBuy == "THB"
    assert order.rate == pytest.approx(0.3977)
    assert order.amountBuy == pytest.approx(7954)
    assert order.displayRate == pytest.approx(1 / 0.3977)
    assert order.displayCurrencySell == "THB"
    assert order.displayCurrencyBuy == "RUB"
    assert order.contactTelegram == "customer"
    assert order.publicNumber == f"{datetime.now(UTC):%Y%m}0001"
    order_flow.notify_order_created.assert_awaited_once()


@pytest.mark.asyncio
async def test_miniapp_order_creation_does_not_serialize_expired_orm_fields(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Подтверждает создание без сериализации истекшего ORM-поля."""
    client, db_session = api_client
    from app.services import order_flow

    async def expire_order_updated_at(order, *_args, **_kwargs) -> None:
        """Имитирует истечение поля после внешнего побочного эффекта уведомления."""
        db_session.expire(order, ["updatedAt"])

    order_flow.notify_order_created.side_effect = expire_order_updated_at
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "rub",
            "amountSell": 20000,
            "currencyBuy": "thb",
            "amountBuy": 123.45,
            "rate": 9.99,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 201
    assert response.content == b""
    assert (await get_latest_order_for_user(db_session, customer.id)).updatedAt is not None


@pytest.mark.asyncio
async def test_miniapp_order_keeps_saved_order_when_manager_notification_fails(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    from app.services import order_flow

    order_flow.notify_order_created.side_effect = RuntimeError("telegram unavailable")
    _, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "rub",
            "amountSell": 20000,
            "currencyBuy": "thb",
            "amountBuy": 123.45,
            "rate": 9.99,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 201
    stored_order = await get_latest_order_for_user(db_session, customer.id)
    assert stored_order.publicNumber
    order_flow.notify_order_created.assert_awaited_once()


@pytest.mark.asyncio
async def test_miniapp_order_calculates_external_atxg_withdrawal_on_server(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "THB",
            "amountBuy": 999999,
            "rate": 999999,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 201
    order = await get_latest_order_for_user(db_session, customer.id)
    assert order.currencySell == "ATXG"
    assert order.currencyBuy == "THB"
    assert order.rate == pytest.approx(35.114)
    assert order.amountBuy == pytest.approx(14045.6)

    wallet = await db_session.scalar(select(AexWallet).where(AexWallet.user_id == customer.id))
    assert wallet is not None
    assert wallet.balance_available == 600
    assert wallet.balance_reserved == 400

    entries = (
        (
            await db_session.execute(
                select(AexLedgerEntry).where(AexLedgerEntry.wallet_id == wallet.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(entry.entry_type, entry.amount, entry.reference_type) for entry in entries] == [
        ("hold", 400, "order_withdraw_hold")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("currency_buy", "amount_buy", "rate"),
    [("USDT", 400.0, 1.0), ("RUB", 30400.0, 76.0)],
)
async def test_miniapp_order_accepts_internal_atxg_payout(
    api_client: tuple[AsyncClient, AsyncSession],
    currency_buy: str,
    amount_buy: float,
    rate: float,
) -> None:
    """Внутренняя ATXG-выплата сохраняет псевдострану и резервирует баланс."""
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    db_session.add(Rate(currency="USDTRUB", price=80.0, margin=5.0, country=None, is_internal=True))
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "internal",
            "cityId": None,
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": currency_buy,
            "amountBuy": amount_buy,
            "rate": rate,
            "methodGet": "bank_account",
        },
    )

    assert response.status_code == 201
    order = await get_latest_order_for_user(db_session, customer.id)
    assert order.country is Country.INTERNAL
    assert order.methodGet == "bank_account"
    wallet = await db_session.scalar(select(AexWallet).where(AexWallet.user_id == customer.id))
    assert wallet is not None
    assert wallet.balance_available == 600
    assert wallet.balance_reserved == 400


@pytest.mark.asyncio
async def test_miniapp_internal_payout_recalculates_client_quote(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Внутренняя выплата не должна принимать курс и сумму из payload клиента."""
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "internal",
            "cityId": None,
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "USDT",
            "amountBuy": 999999,
            "rate": 999999,
            "methodGet": "bank_account",
        },
    )

    assert response.status_code == 201
    order = await get_latest_order_for_user(db_session, customer.id)
    assert order.amountBuy == pytest.approx(400)
    assert order.rate == pytest.approx(1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"currencySell": "RUB"},
        {"country": "thailand"},
        {"methodGet": "qrcode"},
        {"cityId": 1},
        {"currencyBuy": "THB"},
    ],
)
async def test_miniapp_order_rejects_invalid_internal_payout_contract(
    api_client: tuple[AsyncClient, AsyncSession],
    overrides: dict[str, object],
) -> None:
    """Внутренняя страна не должна обходить ограничения пары, метода и города."""
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    payload: dict[str, object] = {
        "country": "internal",
        "cityId": None,
        "currencySell": "ATXG",
        "amountSell": 400,
        "currencyBuy": "USDT",
        "amountBuy": 400,
        "rate": 1.0,
        "methodGet": "bank_account",
    }
    payload.update(overrides)
    if overrides.get("cityId") == 1:
        payload["cityId"] = city.id

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )

    assert response.status_code == 422
    assert await db_session.scalar(select(func.count(Order.id))) == 0


@pytest.mark.asyncio
async def test_miniapp_order_rejects_non_positive_internal_rub_rate(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    """Нулевая внутренняя пара не разрешает прямой API-обход Mini App."""
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    db_session.add(Rate(currency="USDTRUB", price=0.0, margin=3.0, country=None, is_internal=True))
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "internal",
            "cityId": None,
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "RUB",
            "amountBuy": 1,
            "rate": 1,
            "methodGet": "bank_account",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "RATE_PAIR_UNAVAILABLE"
    assert await db_session.scalar(select(func.count(Order.id))) == 0
    wallet = await db_session.scalar(select(AexWallet).where(AexWallet.user_id == customer.id))
    assert wallet is not None
    assert wallet.balance_available == 1000
    assert wallet.balance_reserved == 0


@pytest.mark.asyncio
async def test_miniapp_aex_order_rejects_missing_usdt_based_pair_without_mutation(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "EUR",
            "amountBuy": 100,
            "rate": 0.01,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "RATE_PAIR_UNAVAILABLE"
    assert await db_session.scalar(select(func.count(Order.id))) == 0
    assert await db_session.scalar(select(func.count(AexWallet.id))) == 1
    assert await db_session.scalar(select(func.count(AexLedgerEntry.id))) == 0


@pytest.mark.asyncio
async def test_miniapp_aex_order_rejects_missing_usdt_based_pair_before_wallet_lookup(
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
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "EUR",
            "amountBuy": 100,
            "rate": 0.01,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "RATE_PAIR_UNAVAILABLE"
    assert await db_session.scalar(select(func.count(Order.id))) == 0
    assert await db_session.scalar(select(func.count(AexWallet.id))) == 0
    assert await db_session.scalar(select(func.count(AexLedgerEntry.id))) == 0


@pytest.mark.asyncio
async def test_miniapp_aex_order_uses_usdt_minimum_amount(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 299,
            "currencyBuy": "THB",
            "amountBuy": 10823.8,
            "rate": 36.2,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "MIN_AMOUNT"
    assert response.json()["params"] == {
        "minAmount": 300,
        "method": "qrcode",
        "currency": "ATXG",
    }
    assert await db_session.scalar(select(func.count(Order.id))) == 0
    assert await db_session.scalar(select(func.count(AexLedgerEntry.id))) == 0


@pytest.mark.asyncio
async def test_miniapp_aex_order_rejects_amount_above_available_balance(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 350)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "THB",
            "amountBuy": 14480,
            "rate": 36.2,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ATXG_INSUFFICIENT_BALANCE"
    assert await db_session.scalar(select(func.count(Order.id))) == 0
    assert await db_session.scalar(select(func.count(AexLedgerEntry.id))) == 0


@pytest.mark.asyncio
async def test_miniapp_aex_order_rejects_when_withdraw_limit_not_reached(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 50)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 300,
            "currencyBuy": "THB",
            "amountBuy": 10860,
            "rate": 36.2,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ATXG_WITHDRAW_LIMIT_NOT_REACHED"
    assert await db_session.scalar(select(func.count(Order.id))) == 0
    assert await db_session.scalar(select(func.count(AexLedgerEntry.id))) == 0


@pytest.mark.asyncio
async def test_miniapp_aex_order_rolls_back_order_when_hold_fails(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    from app.services import order_flow

    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    from app.services.aex import AexService

    class _FailingAexService(AexService):
        async def hold_order_withdrawal(self, *args, **kwargs):
            raise RuntimeError("hold failed")

    monkeypatch.setattr(order_flow, "AexService", _FailingAexService, raising=False)

    with pytest.raises(RuntimeError, match="hold failed"):
        await client.post(
            "/api/miniapp/orders",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "country": "thailand",
                "currencySell": "ATXG",
                "amountSell": 400,
                "currencyBuy": "THB",
                "amountBuy": 14480,
                "rate": 36.2,
                "methodGet": "qrcode",
            },
        )

    await db_session.rollback()
    assert await db_session.scalar(select(func.count(Order.id))) == 0
    assert await db_session.scalar(select(func.count(AexLedgerEntry.id))) == 0


@pytest.mark.asyncio
async def test_completed_aex_order_debits_reserved_balance(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    from app.services import order_status
    from app.services.order_status import update_order_status

    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    monkeypatch.setattr(order_status, "notify_order_status_changed", AsyncMock())

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "THB",
            "amountBuy": 14480,
            "rate": 36.2,
            "methodGet": "qrcode",
        },
    )
    assert response.status_code == 201
    order_id = (await get_latest_order_for_user(db_session, customer.id)).id

    updated = await update_order_status(db_session, order_id=order_id, status=OrderStatus.COMPLETED)

    wallet = await db_session.scalar(select(AexWallet).where(AexWallet.user_id == customer.id))
    assert updated.status == int(OrderStatus.COMPLETED)
    assert wallet is not None
    assert wallet.balance_available == 600
    assert wallet.balance_reserved == 0
    entries = (
        await db_session.execute(
            select(AexLedgerEntry.entry_type, AexLedgerEntry.reference_type).where(
                AexLedgerEntry.wallet_id == wallet.id
            )
        )
    ).all()
    assert entries == [("hold", "order_withdraw_hold"), ("debit", "order_withdraw_debit")]


@pytest.mark.asyncio
async def test_cancelled_aex_order_releases_reserved_balance(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    from app.services import order_status
    from app.services.order_status import update_order_status

    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    monkeypatch.setattr(order_status, "notify_order_status_changed", AsyncMock())

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "THB",
            "amountBuy": 14480,
            "rate": 36.2,
            "methodGet": "qrcode",
        },
    )
    assert response.status_code == 201
    order_id = (await get_latest_order_for_user(db_session, customer.id)).id

    updated = await update_order_status(db_session, order_id=order_id, status=OrderStatus.CANCELLED)

    wallet = await db_session.scalar(select(AexWallet).where(AexWallet.user_id == customer.id))
    assert updated.status == int(OrderStatus.CANCELLED)
    assert wallet is not None
    assert wallet.balance_available == 1000
    assert wallet.balance_reserved == 0
    entries = (
        await db_session.execute(
            select(AexLedgerEntry.entry_type, AexLedgerEntry.reference_type).where(
                AexLedgerEntry.wallet_id == wallet.id
            )
        )
    ).all()
    assert entries == [("hold", "order_withdraw_hold"), ("release", "order_withdraw_release")]


@pytest.mark.asyncio
async def test_aex_order_status_retry_does_not_mutate_balance_twice(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    from app.services import order_status
    from app.services.order_status import update_order_status

    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    monkeypatch.setattr(order_status, "notify_order_status_changed", AsyncMock())

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "THB",
            "amountBuy": 14480,
            "rate": 36.2,
            "methodGet": "qrcode",
        },
    )
    assert response.status_code == 201
    order_id = (await get_latest_order_for_user(db_session, customer.id)).id

    await update_order_status(db_session, order_id=order_id, status=OrderStatus.COMPLETED)
    await update_order_status(db_session, order_id=order_id, status=OrderStatus.COMPLETED)

    wallet = await db_session.scalar(select(AexWallet).where(AexWallet.user_id == customer.id))
    assert wallet is not None
    assert wallet.balance_available == 600
    assert wallet.balance_reserved == 0
    assert await db_session.scalar(select(func.count(AexLedgerEntry.id))) == 2


@pytest.mark.asyncio
async def test_completed_aex_order_rejects_later_cancellation_without_balance_mutation(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    from app.services import order_status
    from app.services.order_status import update_order_status

    _, _, customer = await seed_exchange_data(db_session)
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    monkeypatch.setattr(order_status, "notify_order_status_changed", AsyncMock())

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "THB",
            "amountBuy": 14480,
            "rate": 36.2,
            "methodGet": "qrcode",
        },
    )
    assert response.status_code == 201
    order_id = (await get_latest_order_for_user(db_session, customer.id)).id
    await update_order_status(db_session, order_id=order_id, status=OrderStatus.COMPLETED)

    with pytest.raises(AntExException) as exc_info:
        await update_order_status(db_session, order_id=order_id, status=OrderStatus.CANCELLED)

    wallet = await db_session.scalar(select(AexWallet).where(AexWallet.user_id == customer.id))
    order = await db_session.get(Order, order_id)
    assert exc_info.value.code == "ATXG_ORDER_FINAL_STATUS_LOCKED"
    assert order is not None
    assert order.status == int(OrderStatus.COMPLETED)
    assert wallet is not None
    assert wallet.balance_available == 600
    assert wallet.balance_reserved == 0
    assert await db_session.scalar(select(func.count(AexLedgerEntry.id))) == 2


@pytest.mark.asyncio
async def test_completed_aex_order_does_not_credit_referral_bonus(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    from app.services import order_status
    from app.services.order_status import update_order_status

    _, _, customer = await seed_exchange_data(db_session)
    referrer = User(telegram_id=700003, username="referrer", first_name="Referrer")
    db_session.add(referrer)
    await db_session.flush()
    db_session.add(
        UserAcquisition(user_id=customer.id, source_type="referral", referrer_user_id=referrer.id)
    )
    await credit_aex_wallet(db_session, customer.id, 1000)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    monkeypatch.setattr(order_status, "notify_order_status_changed", AsyncMock())

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "ATXG",
            "amountSell": 400,
            "currencyBuy": "THB",
            "amountBuy": 14480,
            "rate": 36.2,
            "methodGet": "qrcode",
        },
    )
    assert response.status_code == 201
    order_id = (await get_latest_order_for_user(db_session, customer.id)).id

    await update_order_status(db_session, order_id=order_id, status=OrderStatus.COMPLETED)

    referral_entries_count = await db_session.scalar(
        select(func.count(AexLedgerEntry.id)).where(AexLedgerEntry.reference_type == "referral")
    )
    assert referral_entries_count == 0


@pytest.mark.asyncio
async def test_reengagement_order_keeps_referral_bonus_without_marketing_ledger(
    api_client: tuple[AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db_session = api_client
    from app.services import order_status
    from app.services.order_status import update_order_status

    _, _, customer = await seed_exchange_data(db_session)
    db_session.add(Rate(currency="USDTRUB", price=80.0, margin=5.0, country=None, is_internal=True))
    referrer = User(telegram_id=700030, username="referrer_reengagement")
    platform = MarketingPlatform(slug="referral_ads", name="Referral Ads")
    currency = MarketingCurrency(code="MKT", name="Marketing Test")
    db_session.add_all([referrer, platform, currency])
    await db_session.flush()
    db_session.add(
        UserAcquisition(user_id=customer.id, source_type="referral", referrer_user_id=referrer.id)
    )
    campaign = MarketingCampaign(
        code="REENGAGE01",
        name="Reengagement",
        platform_id=platform.id,
        currency_id=currency.id,
        status="active",
    )
    db_session.add(campaign)
    await db_session.flush()
    db_session.add(
        MarketingTouch(
            user_id=customer.id,
            campaign_id=campaign.id,
            user_state="returning",
            touched_at=datetime.now(UTC),
        )
    )
    await db_session.flush()
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    monkeypatch.setattr(order_status, "notify_order_status_changed", AsyncMock())

    response = await client.post(
        "/api/miniapp/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "country": "thailand",
            "currencySell": "RUB",
            "amountSell": 20_000,
            "currencyBuy": "THB",
            "amountBuy": 8_200,
            "rate": 0.41,
            "methodGet": "qrcode",
        },
    )
    assert response.status_code == 201, response.text

    order = await get_latest_order_for_user(db_session, customer.id)
    await update_order_status(db_session, order_id=order.id, status=OrderStatus.COMPLETED)

    reference_types = set(
        (await db_session.execute(select(AexLedgerEntry.reference_type))).scalars().all()
    )
    assert "referral" in reference_types
    assert not any(value and "market" in value.lower() for value in reference_types)
    assert not any(value and "campaign" in value.lower() for value in reference_types)


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
            "amountSell": 20000,
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
            "amountSell": 30000,
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
            "amountSell": 30000,
            "currencyBuy": "thb",
            "amountBuy": 12000,
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
async def test_miniapp_order_non_cash_services_do_not_save_city(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})

    for method in ("bank_account", "pay_services"):
        response = await client.post(
            "/api/miniapp/orders",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "country": "thailand",
                "cityId": city.id,
                "currencySell": "rub",
                "amountSell": 10000,
                "currencyBuy": "thb",
                "amountBuy": 4000,
                "rate": 0.4,
                "methodGet": method,
            },
        )

        assert response.status_code == 201
        order = await get_latest_order_for_user(db_session, customer.id)
        assert order.methodGet == method
        assert order.CityId is None


@pytest.mark.asyncio
async def test_miniapp_order_returns_machine_readable_errors(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    city, _, customer = await seed_exchange_data(db_session)
    token = create_access_token({"sub": str(customer.id), "role": customer.role})
    db_session.add_all(
        [
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
                publicNumber=f"202605{index:04d}",
            )
            for index in range(1, 11)
        ]
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
async def test_miniapp_order_allows_missing_trusted_contact(
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
            "amountSell": 20000,
            "currencyBuy": "THB",
            "amountBuy": 8000,
            "rate": 0.4,
            "methodGet": "qrcode",
        },
    )

    assert response.status_code == 201
    assert (await get_latest_order_for_user(db_session, customer.id)).contactTelegram is None


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
                publicNumber="2026050002",
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
        "UTC",
        now=datetime(2026, 5, 7, 17, 30, tzinfo=UTC),
    )

    assert today_start == datetime(2026, 5, 7, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_miniapp_navigation_by_role(
    api_client: tuple[AsyncClient, AsyncSession],
) -> None:
    client, db_session = api_client
    _, manager, customer = await seed_exchange_data(db_session)

    customer_token = create_access_token({"sub": str(customer.id), "type": "user"})
    manager_token = create_access_token({"sub": str(manager.id), "type": "user"})

    customer_res = await client.get(
        "/api/miniapp/navigation",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert customer_res.status_code == 200
    customer_nav = customer_res.json()
    assert [item["name"] for item in customer_nav] == ["home", "exchange", "history", "profile"]

    manager_res = await client.get(
        "/api/miniapp/navigation",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert manager_res.status_code == 200
    manager_nav = manager_res.json()
    assert [item["name"] for item in manager_nav] == [
        "managerDashboard",
        "managerOrders",
        "managerChats",
        "managerSettings",
    ]
    assert [item["route"] for item in manager_nav] == [
        "managerDashboard",
        "managerOrders",
        "managerChats",
        "managerProfile",
    ]
    assert manager_nav[2]["badge_key"] == "unread_chats"
