"""Тесты модуля рассылок."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.deps import MINIAPP_GUEST_USER_ID
from app.core.config import settings
from app.core.security import create_access_token
from app.models.admin import Admin
from app.models.user import User


@pytest.fixture
async def seeded_admin(db_session):
    admin = Admin(username=f"admin_{uuid4().hex[:8]}", password_hash="hash")
    db_session.add(admin)
    await db_session.flush()
    return admin


@pytest.fixture
async def seeded_users(db_session):
    users = [
        User(
            id=101,
            username="alpha",
            first_name="Alpha",
            is_bot=False,
            chatId=None,
            role=1,
            is_premium=False,
        ),
        User(
            id=102,
            username="beta",
            first_name="Beta",
            is_bot=False,
            chatId=900102,
            role=1,
            is_premium=True,
        ),
        User(
            id=103,
            username="service-bot",
            first_name="Bot",
            is_bot=True,
            chatId=900103,
            role=1,
            is_premium=False,
        ),
        User(
            id=MINIAPP_GUEST_USER_ID,
            username="guest",
            first_name="Guest",
            is_bot=False,
            chatId=None,
            role=1,
            is_premium=False,
        ),
    ]
    db_session.add_all(users)
    await db_session.flush()
    return users


@pytest.fixture
def admin_headers(monkeypatch: pytest.MonkeyPatch, seeded_admin: Admin) -> dict[str, str]:
    monkeypatch.setattr(settings, "jwt_secret", "broadcast-test-secret-0123456789abcdef")
    token = create_access_token({"sub": str(seeded_admin.id), "type": "admin"})
    return {"Authorization": f"Bearer {token}"}
@pytest.mark.asyncio
async def test_audience_provider_skips_bots_and_guest(db_session, seeded_users) -> None:
    from app.modules.broadcasts.audience import TelegramUserAudienceProvider

    provider = TelegramUserAudienceProvider(db_session)

    recipients = await provider.list_recipients()

    assert [recipient.user_id for recipient in recipients] == [101, 102]
    assert [recipient.chat_id for recipient in recipients] == [101, 900102]


@pytest.mark.asyncio
async def test_deliver_recipients_counts_success_failures_and_escapes_plain_text(
    seeded_users,
) -> None:
    from app.modules.broadcasts.audience import BroadcastRecipient
    from app.modules.broadcasts.runner import deliver_recipients

    recipients = [
        BroadcastRecipient(user_id=101, chat_id=101),
        BroadcastRecipient(user_id=102, chat_id=900102),
    ]

    class FakeSender:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def send_message(
            self,
            *,
            chat_id: int,
            text: str,
            button_text: str | None,
            button_url: str | None,
            allow_paid_broadcast: bool,
        ) -> None:
            self.calls.append(
                {
                    "chat_id": chat_id,
                    "text": text,
                    "button_text": button_text,
                    "button_url": button_url,
                    "allow_paid_broadcast": allow_paid_broadcast,
                }
            )
            if chat_id == 900102:
                raise TelegramForbiddenError(
                    method=SendMessage(chat_id=chat_id, text=text),
                    message="blocked",
                )

    sender = FakeSender()

    success_count, failed_count = await deliver_recipients(
        recipients=recipients,
        sender=sender,
        text="<b>Привет</b>",
        text_format="plain",
        button_text="Открыть",
        button_url="https://example.com",
        allow_paid_broadcast=False,
        target_rps=100000,
        worker_count=8,
    )

    assert success_count == 1
    assert failed_count == 1
    assert sender.calls[0]["text"] == "&lt;b&gt;Привет&lt;/b&gt;"
    assert sender.calls[0]["allow_paid_broadcast"] is False


@pytest.mark.asyncio
async def test_deliver_recipients_pauses_and_retries_after_retry_after(
    seeded_users,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.broadcasts import runner as broadcast_runner
    from app.modules.broadcasts.audience import BroadcastRecipient

    recipients = [
        BroadcastRecipient(user_id=101, chat_id=101),
        BroadcastRecipient(user_id=102, chat_id=900102),
    ]
    sleep_delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)
        return None

    monkeypatch.setattr(broadcast_runner.asyncio, "sleep", fake_sleep)

    class RetrySender:
        def __init__(self) -> None:
            self.calls = 0

        async def send_message(
            self,
            *,
            chat_id: int,
            text: str,
            button_text: str | None,
            button_url: str | None,
            allow_paid_broadcast: bool,
        ) -> None:
            del button_text, button_url
            self.calls += 1
            if self.calls == 1:
                raise TelegramRetryAfter(
                    method=SendMessage(
                        chat_id=chat_id,
                        text=text,
                        allow_paid_broadcast=allow_paid_broadcast,
                    ),
                    message="Too Many Requests",
                    retry_after=2,
                )

    sender = RetrySender()

    success_count, failed_count = await broadcast_runner.deliver_recipients(
        recipients=recipients,
        sender=sender,
        text="<b>Paid</b>",
        text_format="html",
        button_text=None,
        button_url=None,
        allow_paid_broadcast=True,
        target_rps=100000,
        worker_count=64,
    )

    assert success_count == 2
    assert failed_count == 0
    assert sleep_delays[0] == pytest.approx(2.0)
    assert sender.calls >= 3


@pytest.mark.asyncio
async def test_deliver_recipients_preserves_counts_when_sender_crashes() -> None:
    from app.modules.broadcasts.audience import BroadcastRecipient
    from app.modules.broadcasts.runner import BroadcastDeliveryError, deliver_recipients

    recipients = [
        BroadcastRecipient(user_id=1, chat_id=1),
        BroadcastRecipient(user_id=2, chat_id=2),
        BroadcastRecipient(user_id=3, chat_id=3),
    ]

    class FlakySender:
        def __init__(self) -> None:
            self.calls = 0

        async def send_message(
            self,
            *,
            chat_id: int,
            text: str,
            button_text: str | None,
            button_url: str | None,
            allow_paid_broadcast: bool,
        ) -> None:
            del chat_id, text, button_text, button_url, allow_paid_broadcast
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("boom")

    with pytest.raises(BroadcastDeliveryError) as exc_info:
        await deliver_recipients(
            recipients=recipients,
            sender=FlakySender(),
            text="hello",
            text_format="plain",
            button_text=None,
            button_url=None,
            allow_paid_broadcast=False,
            target_rps=100000,
            worker_count=1,
        )

    assert exc_info.value.success_count == 1
    assert exc_info.value.failed_count == 1


@pytest.mark.asyncio
async def test_deliver_recipients_limits_in_flight_workers_to_worker_count() -> None:
    from app.modules.broadcasts.audience import BroadcastRecipient
    from app.modules.broadcasts.runner import deliver_recipients

    recipients = [
        BroadcastRecipient(user_id=index, chat_id=index)
        for index in range(1, 11)
    ]
    active_calls = 0
    max_active_calls = 0
    lock = asyncio.Lock()
    gate = asyncio.Event()
    released = 0

    class SlowSender:
        async def send_message(
            self,
            *,
            chat_id: int,
            text: str,
            button_text: str | None,
            button_url: str | None,
            allow_paid_broadcast: bool,
        ) -> None:
            nonlocal active_calls, max_active_calls, released
            del chat_id, text, button_text, button_url, allow_paid_broadcast
            async with lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
                released += 1
                if released >= 3:
                    gate.set()
            await gate.wait()
            async with lock:
                active_calls -= 1

    await deliver_recipients(
        recipients=recipients,
        sender=SlowSender(),
        text="hello",
        text_format="plain",
        button_text=None,
        button_url=None,
        allow_paid_broadcast=False,
        target_rps=100000,
        worker_count=3,
    )

    assert max_active_calls == 3


@pytest.mark.asyncio
async def test_create_broadcast_endpoint_saves_record_and_schedules_runner(
    client,
    db_session,
    admin_headers: dict[str, str],
    seeded_admin: Admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.broadcasts.models import Broadcast

    scheduled_ids: list[int] = []

    async def fake_schedule(*, broadcast_id: int) -> None:
        scheduled_ids.append(broadcast_id)

    monkeypatch.setattr("app.api.routers.broadcasts.schedule_broadcast", fake_schedule)

    response = await client.post(
        "/api/admin/broadcasts",
        headers=admin_headers,
        json={
            "text": "Тестовая рассылка",
            "format": "plain",
            "button_text": None,
            "button_url": None,
            "speed_mode": "free",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["speed_mode_requested"] == "free"
    assert scheduled_ids == [payload["id"]]

    stored = await db_session.get(Broadcast, payload["id"])
    assert stored is not None
    assert stored.created_by_admin_id == seeded_admin.id


@pytest.mark.asyncio
async def test_recover_stale_broadcasts_marks_active_rows_failed(
    db_session,
    seeded_admin: Admin,
) -> None:
    from app.modules.broadcasts.models import Broadcast
    from app.modules.broadcasts.runner import recover_stale_broadcasts_on_startup

    await db_session.execute(delete(Broadcast))
    await db_session.flush()

    running = Broadcast(
        text="running",
        format="plain",
        button_text=None,
        button_url=None,
        status="running",
        audience_type="all_non_bot_users",
        speed_mode_requested="free",
        speed_mode_effective="free",
        target_rps=28,
        worker_count=8,
        total_count=10,
        success_count=3,
        failed_count=1,
        created_by_admin_id=seeded_admin.id,
    )
    completed = Broadcast(
        text="completed",
        format="plain",
        button_text=None,
        button_url=None,
        status="completed",
        audience_type="all_non_bot_users",
        speed_mode_requested="free",
        speed_mode_effective="free",
        target_rps=28,
        worker_count=8,
        total_count=4,
        success_count=4,
        failed_count=0,
        created_by_admin_id=seeded_admin.id,
    )
    db_session.add_all([running, completed])
    await db_session.commit()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    await recover_stale_broadcasts_on_startup(session_factory=session_factory)

    await db_session.refresh(running)
    await db_session.refresh(completed)

    assert running.status == "failed"
    assert running.last_error is not None
    assert "перезапуск" in running.last_error.lower()
    assert running.finished_at is not None
    assert completed.status == "completed"


@pytest.mark.asyncio
async def test_recover_stale_broadcasts_skips_when_table_is_missing() -> None:
    from app.modules.broadcasts.runner import recover_stale_broadcasts_on_startup

    class FakeConnection:
        async def run_sync(self, fn):
            class SyncConnection:
                pass

            return fn(SyncConnection())

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def connection(self):
            return FakeConnection()

    await recover_stale_broadcasts_on_startup(
        session_factory=lambda: FakeSession(),
        has_table_check=lambda _sync_conn, _table_name: False,
    )


def test_broadcast_create_rejects_invalid_button_url() -> None:
    from pydantic import ValidationError

    from app.modules.broadcasts.schemas import BroadcastCreate

    with pytest.raises(ValidationError):
        BroadcastCreate(
            text="hello",
            format="html",
            button_text="Open",
            button_url="example.com",
        )

    payload = BroadcastCreate(
        text="hello",
        format="html",
        button_text="Open",
        button_url="https://example.com",
    )
    parsed = urlparse(payload.button_url or "")

    assert parsed.scheme == "https"


@pytest.mark.asyncio
async def test_list_broadcasts_returns_newest_first(
    client,
    db_session,
    admin_headers: dict[str, str],
    seeded_admin: Admin,
) -> None:
    from app.modules.broadcasts.models import Broadcast

    await db_session.execute(delete(Broadcast))
    await db_session.flush()

    older = Broadcast(
        text="older",
        format="plain",
        button_text=None,
        button_url=None,
        status="completed",
        audience_type="all_non_bot_users",
        speed_mode_requested="free",
        speed_mode_effective="free",
        target_rps=28,
        worker_count=8,
        total_count=10,
        success_count=10,
        failed_count=0,
        created_by_admin_id=seeded_admin.id,
        createdAt=datetime(2029, 3, 29, 10, 0, tzinfo=UTC),
        updatedAt=datetime(2029, 3, 29, 10, 0, tzinfo=UTC),
    )
    newer = Broadcast(
        text="newer",
        format="plain",
        button_text=None,
        button_url=None,
        status="failed",
        audience_type="all_non_bot_users",
        speed_mode_requested="paid",
        speed_mode_effective="paid",
        target_rps=1000,
        worker_count=64,
        total_count=20,
        success_count=5,
        failed_count=0,
        created_by_admin_id=seeded_admin.id,
        createdAt=datetime(2030, 3, 30, 10, 0, tzinfo=UTC),
        updatedAt=datetime(2030, 3, 30, 10, 0, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    await db_session.flush()

    response = await client.get("/api/admin/broadcasts", headers=admin_headers, params={"limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert [item["text"] for item in payload] == ["newer", "older"]


@pytest.mark.asyncio
async def test_active_broadcast_unique_index_blocks_second_pending_record(
    db_session,
    seeded_admin: Admin,
) -> None:
    from app.modules.broadcasts.models import Broadcast

    await db_session.execute(delete(Broadcast))
    await db_session.flush()

    first = Broadcast(
        text="first",
        format="plain",
        button_text=None,
        button_url=None,
        status="pending",
        audience_type="all_non_bot_users",
        speed_mode_requested="free",
        speed_mode_effective="free",
        target_rps=28,
        worker_count=8,
        total_count=0,
        success_count=0,
        failed_count=0,
        created_by_admin_id=seeded_admin.id,
    )
    second = Broadcast(
        text="second",
        format="plain",
        button_text=None,
        button_url=None,
        status="running",
        audience_type="all_non_bot_users",
        speed_mode_requested="free",
        speed_mode_effective="free",
        target_rps=28,
        worker_count=8,
        total_count=0,
        success_count=0,
        failed_count=0,
        created_by_admin_id=seeded_admin.id,
    )

    db_session.add(first)
    await db_session.flush()
    db_session.add(second)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_create_broadcast_returns_conflict_on_active_broadcast_integrity_error(
    db_session,
    seeded_admin: Admin,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.broadcasts.schemas import BroadcastCreate
    from app.modules.broadcasts.service import create_broadcast

    async def fake_create(*args, **kwargs):
        del args, kwargs
        raise IntegrityError("insert", {}, Exception("uq_broadcast_active_singleton"))

    monkeypatch.setattr("app.modules.broadcasts.repository.BroadcastRepository.create", fake_create)

    with pytest.raises(HTTPException) as exc_info:
        await create_broadcast(
            db_session,
            payload=BroadcastCreate(text="safe", format="plain", speed_mode="free"),
            admin_id=seeded_admin.id,
        )

    assert exc_info.value.status_code == 409


def test_broadcast_model_has_russian_comments() -> None:
    from app.modules.broadcasts.models import Broadcast

    for column in Broadcast.__table__.columns:
        assert column.comment is not None
        assert column.comment.strip()
