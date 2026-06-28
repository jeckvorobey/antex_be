from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.routers.admin import get_today_start_for_timezone
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.order import OrderStatus
from app.enums.user import UserRole
from app.models.admin import Admin
from app.models.aex import AexLedgerEntry, AexWallet
from app.models.city import City
from app.models.config import Config
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
        photo_url="https://t.me/i/userpic/320/customer.jpg",
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
    assert home["rates"]["featured"][0]["calculationRate"] == pytest.approx(0.4)
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
    assert exchange["quote"]["rate"] == 0.4
    assert exchange["quote"]["rateDisplay"] == "0.40"
    assert exchange["quote"]["rateText"] == "1 RUB = 0.40 THB"
    assert exchange["quote"]["amountBuy"] == pytest.approx(5000 * 0.4)
    assert exchange["pairs"][0]["id"] == "rub-thb"
    assert exchange["pairs"][0]["fromCurrency"] == "RUB"
    assert exchange["pairs"][0]["toCurrency"] == "THB"
    assert exchange["pairs"][0]["rate"] == pytest.approx(2.51)
    assert exchange["pairs"][0]["calculationRate"] == pytest.approx(0.4)
    assert exchange["pairs"][0]["rateDisplay"] == "2.51"
    assert exchange["pairs"][0]["rateText"] == "1 THB = 2.51 RUB"
    assert {"rub-gel", "rub-vnd", "usdt-gel", "usdt-vnd"} <= {
        pair["id"] for pair in exchange["pairs"]
    }


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
        referred_by=customer.id,
    )
    db_session.add(referred)
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
    }
    assert "referrals" not in data


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
    assert referral_response.status_code == 200
    assert referral_response.json()["programConfig"] == {
        "referralPercent": "0.35",
        "referralMinWithdraw": "250",
        "referralMaxWithdraw": "5000",
        "aexRate": "1.2",
    }


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
    assert second.status_code == 200
    await db_session.refresh(customer)
    assert customer.referred_by == referrer_one.id


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
) -> None:
    client, db_session = api_client
    _, manager, customer = await seed_exchange_data(db_session)
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
    assert support["href"] == f"https://t.me/{manager.username}"


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
            "amountSell": 20000,
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
    assert order["publicNumber"] == f"{datetime.now(UTC):%Y%m}0001"


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
        order = response.json()
        assert order["methodGet"] == method
        assert order["cityId"] is None
        assert order["city"] is None


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
    order = response.json()
    assert order["contactTelegram"] is None


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
