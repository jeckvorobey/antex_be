"""Регрессии изоляции переписки при смене пользователя-менеджера."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routers.manager import router
from app.api.routers.manager_attachments import router as attachments_router
from app.core.database import get_db_session
from app.core.security import create_access_token
from app.enums.country import Country
from app.enums.user import UserRole
from app.models.chat import ChatAttachment, ChatConversation, ChatMessage
from app.models.order import Order
from app.models.user import User
from app.services.chat import ChatService


@pytest.fixture(autouse=True)
def external_io(monkeypatch):
    """Подменяет только Telegram и Redis, чтобы отказ доступа проверялся без сети."""

    @asynccontextmanager
    async def sender():
        """Имитирует успешную внешнюю доставку при ошибочно разрешённой отправке."""
        yield SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=99)))

    monkeypatch.setattr("app.services.chat.sender_bot", sender)
    monkeypatch.setattr(
        "app.services.chat.manager_realtime_hub.is_viewing", AsyncMock(return_value=False)
    )
    monkeypatch.setattr("app.services.chat.manager_realtime_hub.publish", AsyncMock())
    monkeypatch.setattr(
        "app.services.chat.manager_realtime_hub.is_online", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        "app.services.chat.manager_realtime_hub.set_viewing", AsyncMock(return_value=False)
    )


@pytest.fixture
async def isolated_client(db_session):
    """Использует реальные роуты, JWT и БД без внешнего запуска приложения."""
    app = FastAPI()
    app.include_router(router)
    app.include_router(attachments_router)

    async def database():
        """Предоставляет изолированную тестовую БД."""
        yield db_session

    app.dependency_overrides[get_db_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def auth(user):
    """Выдаёт настоящий пользовательский JWT для проверки роли в БД."""
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'type': 'user'})}"}


@pytest.fixture
async def manager_switch(db_session):
    """Создаёт сообщение A, затем назначает менеджером другого пользователя B."""
    old = User(telegram_id=991001, role=int(UserRole.MANAGER))
    new = User(telegram_id=991002)
    customer = User(telegram_id=991003, first_name="Клиент")
    db_session.add_all([old, new, customer])
    await db_session.flush()
    service = ChatService(db_session)
    message, conversation, _ = await service.capture_inbound(
        user=customer,
        telegram_chat_id=customer.telegram_id,
        telegram_message_id=10,
        message_type="text",
        text="История первого менеджера",
        caption=None,
    )
    outbound = ChatMessage(
        conversation_id=conversation.id,
        direction="outbound",
        message_type="document",
        delivery_status="sent",
        client_request_id="private-key",
        telegram_chat_id=customer.telegram_id,
        telegram_message_id=12,
    )
    db_session.add(outbound)
    await db_session.flush()
    attachment = ChatAttachment(message_id=outbound.id, kind="document", payload=b"private")
    db_session.add(attachment)
    old.role = int(UserRole.USER)
    new.role = int(UserRole.MANAGER)
    await db_session.commit()
    return old, new, customer, message, conversation, attachment


async def test_new_manager_does_not_inherit_history(isolated_client, manager_switch):
    """Замена менеджера не передаёт список, поиск и счётчик старых чатов."""
    _, new, *_ = manager_switch
    for query in ("", "?query=Клиент", "?unreadOnly=true"):
        response = await isolated_client.get("/api/manager/chats" + query, headers=auth(new))
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0, "unreadTotal": 0}


async def test_new_inbound_starts_separate_conversation(db_session, manager_switch):
    """Новый менеджер получает отдельную беседу даже при reply на старое сообщение."""
    _, new, customer, old_message, old_chat, _ = manager_switch
    service = ChatService(db_session)
    message, conversation, _ = await service.capture_inbound(
        user=customer,
        telegram_chat_id=customer.telegram_id,
        telegram_message_id=11,
        message_type="text",
        text="Сообщение для B",
        caption=None,
        reply_to_telegram_message_id=old_message.telegram_message_id,
    )
    assert conversation.id != old_chat.id
    assert conversation.manager_id == new.id
    assert conversation.unread_count == 1
    assert old_chat.unread_count == 1
    assert message.reply_to_message_id is None


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/chats/{chat}", None),
        ("GET", "/chats/{chat}/messages", None),
        ("POST", "/chats/{chat}/read", None),
        ("POST", "/chats/{chat}/close", None),
        ("POST", "/chats/{chat}/messages", {"clientRequestId": "foreign-text-1", "text": "Нет"}),
        ("POST", "/chats/{chat}/attachments/private-key/retry", None),
        ("GET", "/chat-attachments/{attachment}", None),
        ("PUT", "/realtime/viewing", {"connectionId": "00000000-0000-0000-0000-000000000001"}),
    ],
)
async def test_foreign_chat_ids_are_not_accessible(
    isolated_client,
    manager_switch,
    method,
    path,
    body,
):
    """Знание идентификатора не даёт новому менеджеру доступа к старой переписке."""
    _, new, _, _, conversation, attachment = manager_switch
    if path == "/realtime/viewing":
        body = {**body, "conversationId": conversation.id}
    response = await isolated_client.request(
        method,
        "/api/manager" + path.format(chat=conversation.id, attachment=attachment.id),
        headers=auth(new),
        json=body,
    )
    assert response.status_code == 404


async def test_owner_without_manager_role_is_forbidden(isolated_client, manager_switch):
    """Владение чатом не заменяет действующую роль менеджера."""
    old, _, _, _, conversation, _ = manager_switch
    response = await isolated_client.get(
        f"/api/manager/chats/{conversation.id}",
        headers=auth(old),
    )
    assert response.status_code == 403


async def test_unowned_history_is_not_assigned_to_current_manager(
    db_session,
    isolated_client,
):
    """История без доказанного владельца сохраняется, но не выдаётся менеджеру."""
    manager = User(telegram_id=992001, role=int(UserRole.MANAGER))
    customer = User(telegram_id=992002)
    db_session.add_all([manager, customer])
    await db_session.flush()
    archived = ChatConversation(user_id=customer.id, unread_count=9)
    db_session.add(archived)
    await db_session.commit()
    response = await isolated_client.get("/api/manager/chats", headers=auth(manager))
    assert response.json() == {"items": [], "total": 0, "unreadTotal": 0}
    assert await db_session.get(ChatConversation, archived.id) is not None


async def test_forward_cannot_copy_foreign_source_to_own_chat(
    db_session,
    isolated_client,
    manager_switch,
):
    """Собственный получатель не позволяет переслать сообщение прежнего менеджера."""
    _, new, customer, source, _, _ = manager_switch
    own_chat = ChatConversation(user_id=customer.id, manager_id=new.id)
    db_session.add(own_chat)
    await db_session.commit()
    response = await isolated_client.post(
        f"/api/manager/chats/{own_chat.id}/forward",
        headers=auth(new),
        json={"clientRequestId": "foreign-forward-key", "sourceMessageId": source.id},
    )
    assert response.status_code == 404


async def test_upload_cannot_write_foreign_chat(isolated_client, manager_switch):
    """Бинарная загрузка проверяет владельца до обработки тела."""
    _, new, _, _, old_chat, _ = manager_switch
    response = await isolated_client.post(
        f"/api/manager/chats/{old_chat.id}/attachments",
        headers=auth(new),
        params={"clientRequestId": "foreign-upload-key", "filename": "a.pdf", "kind": "document"},
        content=b"private",
    )
    assert response.status_code == 404


async def test_existing_text_key_cannot_return_foreign_message(
    db_session,
    isolated_client,
    manager_switch,
):
    """Повтор известного ключа не возвращает чужой sent-текст в собственную беседу."""
    _, new, customer, _, old_chat, _ = manager_switch
    own_chat = ChatConversation(user_id=customer.id, manager_id=new.id)
    db_session.add_all(
        [
            own_chat,
            ChatMessage(
                conversation_id=old_chat.id,
                direction="outbound",
                message_type="text",
                text="Секрет",
                delivery_status="sent",
                client_request_id="known-text-key",
            ),
        ]
    )
    await db_session.commit()
    response = await isolated_client.post(
        f"/api/manager/chats/{own_chat.id}/messages",
        headers=auth(new),
        json={"clientRequestId": "known-text-key", "text": "Повтор"},
    )
    assert response.status_code == 404
    assert "Секрет" not in response.text


async def test_order_chat_uses_manager_customer_pair(
    db_session,
    isolated_client,
    manager_switch,
):
    """Открытие из заявки разделяет владельцев и сохраняет прежний идентификатор пары."""
    old, new, customer, _, old_chat, _ = manager_switch
    order = Order(
        UserId=customer.id,
        country=Country.THAILAND,
        methodGet="cash",
        publicNumber="ISOLATION01",
        currencySell="RUB",
        amountSell=1000,
        currencyBuy="THB",
        amountBuy=300,
    )
    db_session.add(order)
    await db_session.commit()
    path = f"/api/manager/orders/{order.id}/chat"
    first = await isolated_client.post(path, headers=auth(new))
    repeated = await isolated_client.post(path, headers=auth(new))
    assert first.status_code == 200
    assert first.json()["id"] == repeated.json()["id"] != old_chat.id
    assert first.json()["lastMessage"] is None
    old.role = int(UserRole.MANAGER)
    await db_session.commit()
    restored = await isolated_client.post(path, headers=auth(old))
    assert restored.json()["id"] == old_chat.id
    own_list = await isolated_client.get("/api/manager/chats", headers=auth(new))
    assert [chat["id"] for chat in own_list.json()["items"]] == [first.json()["id"]]


async def test_delayed_old_notifications_never_reach_new_manager(
    db_session,
    manager_switch,
    monkeypatch,
):
    """Отложенная публикация и редактирование сохраняют владельца исходного сообщения."""
    _, _, customer, message, conversation, _ = manager_switch
    delivered_to = []

    @asynccontextmanager
    async def sender():
        """Запоминает адресатов внешней доставки без обращения к Telegram."""

        async def send_message(**kwargs):
            """Фиксирует адресата доставки."""
            delivered_to.append(kwargs["chat_id"])

        yield SimpleNamespace(send_message=send_message)

    monkeypatch.setattr("app.services.chat.sender_bot", sender)
    service = ChatService(db_session)
    await service.publish_message_created(message, conversation)
    await service.capture_edit(
        telegram_chat_id=customer.telegram_id,
        telegram_message_id=10,
        text="Исправленная старая история",
        caption=None,
        telegram_edit_date=None,
    )
    await service.publish_message_updated(message)
    assert delivered_to == []
    assert message.conversation_id == conversation.id
