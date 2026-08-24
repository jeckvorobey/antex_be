from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from starlette.requests import Request

from app.api import deps
from app.api.routers.manager import list_chats, list_manager_orders, update_manager_order_status
from app.api.routers.manager_attachments import upload_chat_attachment
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.order import OrderStatus
from app.enums.user import UserRole
from app.models.chat import ChatConversation, ChatMessage
from app.models.city import City
from app.models.order import Order
from app.models.user import User
from app.repositories.chat import ChatRepository
from app.schemas.chat import ManagerOrderStatusRequest
from app.services.chat import ChatService
from app.services.chat_attachments import send_manager_attachment
from app.services.order_notifications import DeliveryOutcome


async def test_manager_text_idempotency_is_scoped_to_conversation(db_session) -> None:
    first_customer = User(telegram_id=829801)
    second_customer = User(telegram_id=829802)
    db_session.add_all([first_customer, second_customer])
    await db_session.flush()
    first = ChatConversation(user_id=first_customer.id)
    second = ChatConversation(user_id=second_customer.id)
    db_session.add_all([first, second])
    await db_session.flush()
    db_session.add(
        ChatMessage(
            conversation_id=first.id,
            direction="outbound",
            message_type="text",
            text="Первое сообщение",
            telegram_chat_id=first_customer.telegram_id,
            delivery_status="sent",
            client_request_id="shared-request-id",
        )
    )
    await db_session.commit()

    with pytest.raises(LookupError, match="conversation_not_found"):
        await ChatService(db_session).send_manager_message(
            conversation_id=second.id,
            client_request_id="shared-request-id",
            text="Вторая беседа",
        )


async def test_manager_text_is_committed_before_telegram_delivery(db_session, monkeypatch) -> None:
    customer = User(telegram_id=829803)
    db_session.add(customer)
    await db_session.flush()
    conversation = ChatConversation(user_id=customer.id)
    db_session.add(conversation)
    await db_session.commit()

    commit_completed = False
    original_commit = db_session.commit

    async def tracked_commit() -> None:
        nonlocal commit_completed
        await original_commit()
        commit_completed = True

    class FakeBot:
        async def send_message(self, **_kwargs):
            assert commit_completed
            return SimpleNamespace(message_id=829804)

    @asynccontextmanager
    async def fake_sender_bot():
        yield FakeBot()

    monkeypatch.setattr(db_session, "commit", tracked_commit)
    monkeypatch.setattr("app.services.chat.sender_bot", fake_sender_bot)

    message, _conversation, created = await ChatService(db_session).send_manager_message(
        conversation_id=conversation.id,
        client_request_id="durable-text-request",
        text="Проверка durable idempotency",
    )

    assert created is True
    assert message.delivery_status == "sent"


async def test_manager_orders_include_backend_location_and_customer_name(db_session) -> None:
    """Manager DTO carries persisted location and customer identity for the card."""
    manager = User(telegram_id=829900, role=int(UserRole.MANAGER))
    customer = User(
        telegram_id=829901,
        username="not-the-card-title",
        first_name="Сергей",
        last_name="Иванов",
    )
    city = City(name="Паттайя", country=Country.THAILAND)
    db_session.add_all([manager, customer, city])
    await db_session.flush()
    db_session.add_all(
        [
            Order(
                UserId=customer.id,
                CityId=city.id,
                country=Country.THAILAND,
                currencySell="RUB",
                amountSell=150_000,
                currencyBuy="THB",
                amountBuy=52_350,
                status=int(OrderStatus.CREATED),
                methodGet="cash",
                publicNumber="MC8299001",
            ),
            Order(
                UserId=customer.id,
                CityId=None,
                country=Country.VIETNAM,
                currencySell="RUB",
                amountSell=20_000,
                currencyBuy="VND",
                amountBuy=5_979_619.21,
                status=int(OrderStatus.PROCESSING),
                methodGet="qrcode",
                publicNumber="MC8299002",
            ),
        ]
    )
    await db_session.commit()

    payload = await list_manager_orders(db=db_session, manager=manager)
    items = {item.publicNumber: item for item in payload.items}

    with_city = items["MC8299001"]
    assert with_city.country == "thailand"
    assert with_city.city is not None
    assert with_city.city.model_dump() == {
        "id": city.id,
        "name": "Паттайя",
        "country": Country.THAILAND,
        "countryRuName": "Таиланд",
        "countryCode": "th",
        "countryFlag": "🇹🇭",
    }
    assert with_city.user is not None
    assert with_city.user.firstName == "Сергей"
    assert with_city.user.lastName == "Иванов"

    without_city = items["MC8299002"]
    assert without_city.country == "vietnam"
    assert without_city.city is None


async def test_status_endpoint_commits_new_notification_id_without_write_access_change(
    db_session,
    monkeypatch,
) -> None:
    """Новый Telegram message id сохраняется даже при неизменном write-access."""
    customer = User(telegram_id=830001, telegram_write_access=True)
    manager = User(telegram_id=830002, role=int(UserRole.MANAGER))
    db_session.add_all([customer, manager])
    await db_session.flush()
    order = Order(
        UserId=customer.id,
        user=customer,
        country=Country.THAILAND,
        currencySell="RUB",
        amountSell=10_000,
        currencyBuy="THB",
        amountBuy=3_500,
        status=int(OrderStatus.PROCESSING),
        methodGet="cash",
        publicNumber="MC830001",
        userNotificationMessageId=None,
    )
    db_session.add(order)
    await db_session.commit()

    async def fake_update_order_status(*_args, **_kwargs):
        return order

    async def fake_notify_order_status_changed(target_order, **_kwargs):
        target_order.userNotificationMessageId = 987
        return DeliveryOutcome.SENT

    async def fake_publish(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.api.routers.manager.update_order_status",
        fake_update_order_status,
    )
    monkeypatch.setattr(
        "app.api.routers.manager.notify_order_status_changed",
        fake_notify_order_status_changed,
    )
    monkeypatch.setattr("app.api.routers.manager.manager_realtime_hub.publish", fake_publish)

    await update_manager_order_status(
        order_id=order.id,
        body=ManagerOrderStatusRequest(status=int(OrderStatus.PROCESSING)),
        db=db_session,
        manager=manager,
    )

    await db_session.rollback()
    await db_session.refresh(order)
    assert order.userNotificationMessageId == 987


async def test_chat_list_bulk_enrichment_has_bounded_query_count(db_session) -> None:
    """Страница чатов не добавляет message/order queries для каждого элемента."""
    manager = User(telegram_id=831000, role=int(UserRole.MANAGER))
    db_session.add(manager)
    for index in range(5):
        customer = User(telegram_id=831100 + index, username=f"customer_{index}")
        db_session.add(customer)
        await db_session.flush()
        conversation = ChatConversation(user_id=customer.id, unread_count=index)
        db_session.add(conversation)
        await db_session.flush()
        db_session.add(
            ChatMessage(
                conversation_id=conversation.id,
                direction="inbound",
                message_type="text",
                text=f"Сообщение {index}",
                telegram_chat_id=customer.telegram_id,
                telegram_message_id=100 + index,
                delivery_status="received",
            )
        )
        db_session.add(
            Order(
                UserId=customer.id,
                country=Country.THAILAND,
                currencySell="RUB",
                amountSell=10_000 + index,
                currencyBuy="THB",
                amountBuy=3_500 + index,
                status=int(OrderStatus.CREATED),
                methodGet="cash",
                publicNumber=f"MC83{index:04d}",
            )
        )
    await db_session.commit()

    queries = 0

    def count_query(*_args) -> None:
        nonlocal queries
        queries += 1

    assert db_session.bind is not None
    event.listen(db_session.bind.sync_engine, "before_cursor_execute", count_query)
    try:
        payload = await list_chats(
            db=db_session,
            manager=manager,
            unreadOnly=False,
            query=None,
            limit=50,
            offset=0,
        )
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", count_query)

    assert len(payload.items) == 5
    assert {item.lastMessage.text for item in payload.items if item.lastMessage} == {
        f"Сообщение {index}" for index in range(5)
    }
    assert {item.latestOrder.publicNumber for item in payload.items if item.latestOrder} == {
        f"MC83{index:04d}" for index in range(5)
    }
    assert queries <= 8


async def test_manager_chat_endpoint_allows_manager_and_rejects_user(
    db_session,
    monkeypatch,
) -> None:
    """Реальный manager endpoint возвращает MANAGER 200 и USER 403."""
    from app.main import app

    manager = User(telegram_id=832001, role=int(UserRole.MANAGER))
    customer = User(telegram_id=832002, role=int(UserRole.USER))
    db_session.add_all([manager, customer])
    await db_session.commit()
    monkeypatch.setattr(settings, "jwt_secret", "manager-chat-api-test-secret-32-bytes")

    async def override_db_session():
        yield db_session

    app.dependency_overrides[deps.get_db_session] = override_db_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            manager_token = create_access_token({"sub": str(manager.id), "role": manager.role})
            user_token = create_access_token({"sub": str(customer.id), "role": customer.role})
            manager_response = await client.get(
                "/api/manager/chats",
                headers={"Authorization": f"Bearer {manager_token}"},
            )
            user_response = await client.get(
                "/api/manager/chats",
                headers={"Authorization": f"Bearer {user_token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert manager_response.status_code == 200
    assert manager_response.json() == {"items": [], "total": 0, "unreadTotal": 0}
    assert user_response.status_code == 403


@pytest.mark.parametrize(
    ("retry_succeeds", "expected_status", "expected_event"),
    [
        (True, "sent", "chat.message.sent"),
        (False, "failed", "chat.message.failed"),
    ],
)
async def test_upload_replay_publishes_retry_delivery_result(
    db_session,
    monkeypatch,
    retry_succeeds: bool,
    expected_status: str,
    expected_event: str,
) -> None:
    """Replay исходного upload публикует новый delivery result в manager realtime."""
    customer = User(telegram_id=833001, telegram_write_access=True)
    manager = User(telegram_id=833002, role=int(UserRole.MANAGER))
    db_session.add_all([customer, manager])
    await db_session.flush()
    conversation, _ = await ChatRepository(db_session).get_or_create_conversation(customer.id)
    sends = 0

    class FakeBot:
        async def send_document(self, *, chat_id: int, document):
            nonlocal sends
            sends += 1
            assert chat_id == 833001
            if sends == 1 or not retry_succeeds:
                raise RuntimeError("temporary Telegram outage")
            return SimpleNamespace(
                message_id=920,
                document=SimpleNamespace(file_id="tg-replay", file_unique_id="tg-replay-unique"),
                photo=None,
                video=None,
                voice=None,
            )

    @asynccontextmanager
    async def fake_sender_bot():
        yield FakeBot()

    monkeypatch.setattr("app.services.chat_attachments.sender_bot", fake_sender_bot)
    failed, _conversation, attempted = await send_manager_attachment(
        db_session,
        conversation_id=conversation.id,
        client_request_id="attachment-upload-replay-1",
        content=b"replay-payload",
        filename="replay.pdf",
        mime_type="application/pdf",
        kind="document",
    )
    await db_session.commit()
    assert attempted is True
    assert failed.delivery_status == "failed"

    published: list[tuple[str, dict[str, object]]] = []

    async def capture_publish(event: str, payload: dict[str, object]) -> None:
        published.append((event, payload))

    monkeypatch.setattr("app.services.chat.manager_realtime_hub.publish", capture_publish)

    body_sent = False

    async def receive() -> dict[str, object]:
        nonlocal body_sent
        if body_sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        body_sent = True
        return {"type": "http.request", "body": b"replay-payload", "more_body": False}

    request = Request(
        {"type": "http", "method": "POST", "path": "/", "headers": []},
        receive,
    )
    response = await upload_chat_attachment(
        conversation_id=conversation.id,
        request=request,
        db=db_session,
        manager=manager,
        client_request_id="attachment-upload-replay-1",
        filename="replay.pdf",
        mime_type="application/pdf",
        kind="document",
    )

    assert sends == 2
    assert response.id == failed.id
    assert response.deliveryStatus == expected_status
    assert len(published) == 1
    assert published[0][0] == expected_event
    assert published[0][1]["message"]["id"] == failed.id
