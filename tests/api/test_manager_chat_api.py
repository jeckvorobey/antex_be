from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.api import deps
from app.api.routers.manager import list_chats, update_manager_order_status
from app.core.config import settings
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.order import OrderStatus
from app.enums.user import UserRole
from app.models.chat import ChatConversation, ChatMessage
from app.models.order import Order
from app.models.user import User
from app.schemas.chat import ManagerOrderStatusRequest
from app.services.order_notifications import DeliveryOutcome


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
