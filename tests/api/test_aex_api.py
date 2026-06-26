"""TDD тесты для API AEX и реферальной системы."""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import create_access_token
from app.models.admin import Admin
from app.models.user import User


@pytest.fixture
async def aex_api_client(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession]]:
    from app.main import app

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[deps.get_db_session] = override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session
    app.dependency_overrides.clear()


def _user_token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id), "type": "user"})


def _admin_token(admin_id: int) -> str:
    return create_access_token({"sub": str(admin_id), "type": "admin"})


# ─── User AEX API ────────────────────────────────────────────────────────────


class TestAexWalletEndpoint:
    async def test_get_wallet_creates_if_missing(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=1000, username="wtest")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        response = await client.get(
            "/api/aex/wallet",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user.id
        assert Decimal(data["balance_available"]) == Decimal("0")
        assert Decimal(data["balance_reserved"]) == Decimal("0")
        assert Decimal(data["balance_total"]) == Decimal("0")

    async def test_get_wallet_requires_auth(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, _ = aex_api_client
        response = await client.get("/api/aex/wallet")
        assert response.status_code == 401


class TestAexOperationsEndpoint:
    async def test_get_operations_empty(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=2000, username="opstest")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        response = await client.get(
            "/api/aex/operations",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["next_cursor"] is None


class TestAexTransferEndpoint:
    async def test_transfer_holds_aex(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=3000, username="transfertest")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        # Credit first
        from app.services.aex import AexService

        await AexService().credit(db, user.id, Decimal("100"))
        await db.commit()

        response = await client.post(
            "/api/aex/transfer",
            json={"amount": "50"},
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    async def test_transfer_rejects_insufficient(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=4000, username="nbaltest")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        response = await client.post(
            "/api/aex/transfer",
            json={"amount": "100"},
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert response.status_code == 422


# ─── Cursor Pagination ───────────────────────────────────────────────────────


class TestAexOperationsCursorPagination:
    """TDD: cursor-based pagination для /api/aex/operations."""

    async def test_first_page_no_cursor(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=60001, username="cursor_first")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        from app.services.aex import AexService

        service = AexService()
        for i in range(5):
            await service.credit(db, user.id, Decimal("10"), description=f"entry_{i}")
        await db.commit()

        response = await client.get(
            "/api/aex/operations?limit=3",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["next_cursor"] is not None
        # Desc order: newest first
        assert data["items"][0]["description"] == "entry_4"

    async def test_second_page_with_cursor(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=60002, username="cursor_second")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        from app.services.aex import AexService

        service = AexService()
        for i in range(5):
            await service.credit(db, user.id, Decimal("10"), description=f"entry_{i}")
        await db.commit()

        # First page
        resp1 = await client.get(
            "/api/aex/operations?limit=3",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )
        cursor = resp1.json()["next_cursor"]

        # Second page
        resp2 = await client.get(
            f"/api/aex/operations?limit=3&cursor={cursor}",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert resp2.status_code == 200
        data = resp2.json()
        assert len(data["items"]) == 2
        assert data["next_cursor"] is None  # Last page

    async def test_empty_result(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=60003, username="cursor_empty")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        response = await client.get(
            "/api/aex/operations?limit=10",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["next_cursor"] is None

    async def test_invalid_cursor_returns_error(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=60004, username="cursor_invalid")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        response = await client.get(
            "/api/aex/operations?limit=10&cursor=abc",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert response.status_code == 422

    async def test_cursor_no_duplicates_or_gaps(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        """Pagination stable: no duplicates, no gaps."""
        client, db = aex_api_client
        user = User(telegram_id=60005, username="cursor_stable")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        from app.services.aex import AexService

        service = AexService()
        ids_seen: list[int] = []
        for i in range(7):
            entry = await service.credit(db, user.id, Decimal("10"), description=f"e{i}")
            ids_seen.append(entry.id)
        await db.commit()

        all_items: list[dict] = []
        cursor = None
        for _ in range(10):  # Safety limit
            url = "/api/aex/operations?limit=3"
            if cursor:
                url += f"&cursor={cursor}"
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            )
            data = resp.json()
            all_items.extend(data["items"])
            cursor = data.get("next_cursor")
            if cursor is None:
                break

        assert len(all_items) == 7
        # No duplicates
        item_ids = [item["id"] for item in all_items]
        assert len(set(item_ids)) == 7


# ─── Referral API ────────────────────────────────────────────────────────────


class TestReferralCodeEndpoint:
    async def test_get_referral_code(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=5000, username="reftest")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        response = await client.get(
            "/api/referral/code",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["referral_code"]) == 8
        assert "ref_" in data["referral_link"]

    async def test_get_referral_code_idempotent(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=6000, username="refidem")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        resp1 = await client.get(
            "/api/referral/code",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )
        resp2 = await client.get(
            "/api/referral/code",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert resp1.json()["referral_code"] == resp2.json()["referral_code"]


class TestReferralBindEndpoint:
    async def test_bind_referral(self, aex_api_client: tuple[AsyncClient, AsyncSession]) -> None:
        client, db = aex_api_client
        referrer = User(telegram_id=7000, username="bindref")
        db.add(referrer)
        await db.flush()
        await db.refresh(referrer)

        # Generate code
        from app.services.referral import ReferralService

        code = await ReferralService().get_or_create_referral_code(db, referrer)
        await db.commit()

        referred = User(telegram_id=8000, username="bindtarget")
        db.add(referred)
        await db.flush()
        await db.refresh(referred)

        response = await client.post(
            "/api/referral/bind",
            json={"referral_code": code},
            headers={"Authorization": f"Bearer {_user_token(referred.id)}"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True


class TestReferralStatsEndpoint:
    async def test_get_referral_stats(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        user = User(telegram_id=9000, username="statstest")
        db.add(user)
        await db.flush()
        await db.refresh(user)

        response = await client.get(
            "/api/referral/stats",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_referrals"] == 0
        assert data["total_earned"] == "0"


# ─── Admin AEX API ───────────────────────────────────────────────────────────


class TestAdminAexRatesEndpoint:
    async def test_admin_list_rates(self, aex_api_client: tuple[AsyncClient, AsyncSession]) -> None:
        client, db = aex_api_client
        admin = Admin(username="aexadmin", email="aex@test.com", password_hash="x")
        db.add(admin)
        await db.flush()
        await db.refresh(admin)

        response = await client.get(
            "/api/admin/aex/rates",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert "global_rate" in data[0]


class TestAdminAexRateSettingsEndpoint:
    async def test_get_admin_rate(self, aex_api_client: tuple[AsyncClient, AsyncSession]) -> None:
        client, db = aex_api_client
        admin = Admin(username="rateadmin", email="rate@test.com", password_hash="x")
        db.add(admin)
        await db.flush()
        await db.refresh(admin)

        response = await client.get(
            "/api/admin/aex/rate",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rate"] == "0.002000"
        assert data["updatedAt"] is not None

    async def test_update_admin_rate(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        admin = Admin(username="rateupd", email="rateupd@test.com", password_hash="x")
        db.add(admin)
        await db.flush()
        await db.refresh(admin)

        response = await client.put(
            "/api/admin/aex/rate",
            json={"rate": "0.25"},
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )

        assert response.status_code == 200
        assert response.json()["rate"] == "0.250000"


class TestAdminAexPersonalRatesEndpoint:
    async def test_personal_rates_crud(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        admin = Admin(username="prateadmin", email="prate@test.com", password_hash="x")
        user = User(telegram_id=13000, username="prateuser", first_name="Partner")
        db.add_all([admin, user])
        await db.flush()
        await db.refresh(admin)
        await db.refresh(user)

        response = await client.get(
            "/api/admin/aex/rates/personal",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )
        assert response.status_code == 200
        assert response.json() == []

        create_response = await client.post(
            "/api/admin/aex/rates/personal",
            json={"userId": user.id, "rate": "0.5"},
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["userId"] == user.id
        assert created["rate"] == "0.500000"

        rate_id = created["id"]
        update_response = await client.patch(
            f"/api/admin/aex/rates/personal/{rate_id}",
            json={"rate": "0.6"},
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["rate"] == "0.600000"

        delete_response = await client.delete(
            f"/api/admin/aex/rates/personal/{rate_id}",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["ok"] is True


class TestAdminAexPartnerRatesEndpoint:
    async def test_partner_rates_crud(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        admin = Admin(username="partneradmin", email="partner@test.com", password_hash="x")
        user = User(telegram_id=14000, username="partneruser", first_name="Partner")
        db.add_all([admin, user])
        await db.flush()
        await db.refresh(admin)
        await db.refresh(user)

        response = await client.get(
            "/api/admin/aex/rates/partner",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )
        assert response.status_code == 200
        assert response.json() == []

        create_response = await client.post(
            "/api/admin/aex/rates/partner",
            json={"userId": user.id, "rate": "1.1"},
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["userId"] == user.id
        assert created["rate"] == "1.100000"

        rate_id = created["id"]
        update_response = await client.patch(
            f"/api/admin/aex/rates/partner/{rate_id}",
            json={"rate": "1.2"},
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["rate"] == "1.200000"

        delete_response = await client.delete(
            f"/api/admin/aex/rates/partner/{rate_id}",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["ok"] is True


class TestAdminAexCreditEndpoint:
    async def test_admin_credit(self, aex_api_client: tuple[AsyncClient, AsyncSession]) -> None:
        client, db = aex_api_client
        admin = Admin(username="credadmin", email="cred@test.com", password_hash="x")
        user = User(telegram_id=10000, username="credituser")
        db.add_all([admin, user])
        await db.flush()
        await db.refresh(admin)
        await db.refresh(user)

        response = await client.post(
            "/api/admin/aex/credit",
            json={"user_id": user.id, "amount": "100", "description": "Test credit"},
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True

        # Verify balance
        from app.services.aex import AexService

        wallet = await AexService().get_balance(db, user.id)
        assert wallet.balance_available == Decimal("100")


class TestAdminAexDebitEndpoint:
    async def test_admin_debit_insufficient(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        admin = Admin(username="debitadmin", email="debit@test.com", password_hash="x")
        user = User(telegram_id=11000, username="debituser")
        db.add_all([admin, user])
        await db.flush()
        await db.refresh(admin)
        await db.refresh(user)

        response = await client.post(
            "/api/admin/aex/debit",
            json={"user_id": user.id, "amount": "50"},
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )

        assert response.status_code == 422


class TestAdminAexWalletsEndpoint:
    async def test_admin_list_wallets(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        admin = Admin(username="walladmin", email="wall@test.com", password_hash="x")
        user = User(telegram_id=12000, username="walluser")
        db.add_all([admin, user])
        await db.flush()
        await db.refresh(admin)
        await db.refresh(user)

        # Create wallet first
        from app.services.aex import AexService

        await AexService().get_or_create_wallet(db, user.id)
        await db.commit()

        response = await client.get(
            "/api/admin/aex/wallets",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["user_id"] == user.id


# ─── Admin Batch Referral Code Generation ────────────────────────────────


class TestAdminGenerateReferralCodes:
    async def test_generates_codes_for_all_users(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        admin = Admin(username="refgen_admin", email="refgen@test.com", password_hash="x")
        user1 = User(telegram_id=50001, username="refgen_u1")
        user2 = User(telegram_id=50002, username="refgen_u2")
        db.add_all([admin, user1, user2])
        await db.flush()
        await db.refresh(admin)
        await db.refresh(user1)
        await db.refresh(user2)

        response = await client.post(
            "/api/admin/aex/generate-referral-codes",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["generated"] == 2

        # Verify codes were actually set
        await db.refresh(user1)
        await db.refresh(user2)
        assert user1.referral_code is not None
        assert user2.referral_code is not None
        assert len(user1.referral_code) == 8
        assert len(user2.referral_code) == 8
        assert user1.referral_code != user2.referral_code

    async def test_rewrites_existing_codes(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        admin = Admin(username="refskip_admin", email="refskip@test.com", password_hash="x")
        user_with_code = User(telegram_id=50003, username="refskip_has", referral_code="EXISTING")
        user_without = User(telegram_id=50004, username="refskip_none")
        db.add_all([admin, user_with_code, user_without])
        await db.flush()
        await db.refresh(admin)

        response = await client.post(
            "/api/admin/aex/generate-referral-codes",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["generated"] == 2

        # Verify existing code was changed
        await db.refresh(user_with_code)
        assert user_with_code.referral_code is not None
        assert user_with_code.referral_code != "EXISTING"

    async def test_rewrites_codes_when_all_have_codes(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, db = aex_api_client
        admin = Admin(username="refzero_admin", email="refzero@test.com", password_hash="x")
        user = User(telegram_id=50005, username="refzero_user", referral_code="HADCODE")
        db.add_all([admin, user])
        await db.flush()
        await db.refresh(admin)

        response = await client.post(
            "/api/admin/aex/generate-referral-codes",
            headers={"Authorization": f"Bearer {_admin_token(admin.id)}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["generated"] == 1

        await db.refresh(user)
        assert user.referral_code != "HADCODE"

    async def test_requires_admin_auth(
        self, aex_api_client: tuple[AsyncClient, AsyncSession]
    ) -> None:
        client, _ = aex_api_client
        response = await client.post("/api/admin/aex/generate-referral-codes")
        assert response.status_code == 401
