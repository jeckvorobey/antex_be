"""Operational API and WebSocket for the Mini App manager workspace."""

from __future__ import annotations

import secrets
from contextlib import suppress

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.api.deps import DbDep, ManagerUser
from app.core.database import create_db_session
from app.enums.order import OrderStatus
from app.enums.user import has_operator_access
from app.repositories.chat import ChatRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.chat import (
    ChatConversationOut,
    ChatListResponse,
    ChatMessageOut,
    ChatMessagesResponse,
    ChatReadResponse,
    ChatSendRequest,
    ManagerOrderListResponse,
    ManagerOrderStatusRequest,
    ManagerOrderSummary,
    SocketTicketResponse,
)
from app.services.chat import ChatService
from app.services.chat_realtime import SOCKET_TICKET_TTL_SECONDS, manager_realtime_hub
from app.services.order_notifications import (
    notify_order_status_changed,
    reconcile_telegram_write_access,
)
from app.services.order_status import update_order_status

router = APIRouter(prefix="/api/manager", tags=["manager"])


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _manager_order_out(order) -> ManagerOrderSummary:
    payload = ChatService.order_out(order)
    customer = getattr(order, "user", None)
    if customer is not None:
        payload = payload.model_copy(update={"user": ChatService.user_out(customer)})
    return payload


@router.get("/chats", response_model=ChatListResponse)
async def list_chats(
    db: DbDep,
    manager: ManagerUser,
    unreadOnly: bool = Query(False),  # noqa: N803
    query: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ChatListResponse:
    del manager
    repo = ChatRepository(db)
    service = ChatService(db)
    conversations, total = await repo.list_conversations(
        unread_only=unreadOnly,
        query=query,
        limit=limit,
        offset=offset,
    )
    items = [await service.conversation_out(item) for item in conversations]
    return ChatListResponse(items=items, total=total, unreadTotal=await repo.unread_total())


@router.get("/chats/{conversation_id}", response_model=ChatConversationOut)
async def get_chat(
    conversation_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> ChatConversationOut:
    del manager
    conversation = await ChatRepository(db).get_conversation(conversation_id)
    if conversation is None:
        raise _not_found("Conversation not found")
    return await ChatService(db).conversation_out(conversation)


@router.get("/chats/{conversation_id}/messages", response_model=ChatMessagesResponse)
async def get_chat_messages(
    conversation_id: int,
    db: DbDep,
    manager: ManagerUser,
    limit: int = Query(50, ge=1, le=100),
    beforeId: int | None = Query(None, ge=1),  # noqa: N803
) -> ChatMessagesResponse:
    del manager
    repo = ChatRepository(db)
    if await repo.get_conversation(conversation_id) is None:
        raise _not_found("Conversation not found")
    messages, has_more = await repo.list_messages(
        conversation_id,
        limit=limit,
        before_id=beforeId,
    )
    return ChatMessagesResponse(
        items=[ChatService.message_out(message) for message in messages],
        hasMore=has_more,
    )


@router.post("/chats/{conversation_id}/messages", response_model=ChatMessageOut)
async def send_chat_message(
    conversation_id: int,
    body: ChatSendRequest,
    db: DbDep,
    manager: ManagerUser,
) -> ChatMessageOut:
    del manager
    service = ChatService(db)
    try:
        message, conversation, created = await service.send_manager_message(
            conversation_id=conversation_id,
            client_request_id=body.clientRequestId,
            text=body.text,
            reply_to_message_id=body.replyToMessageId,
        )
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    await db.commit()
    if created:
        await service.publish_outbound(message, conversation)
    return service.message_out(message)


@router.post("/chats/{conversation_id}/read", response_model=ChatReadResponse)
async def mark_chat_read(
    conversation_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> ChatReadResponse:
    del manager
    service = ChatService(db)
    try:
        conversation = await service.mark_read(conversation_id)
    except LookupError as exc:
        raise _not_found("Conversation not found") from exc
    await db.commit()
    await service.publish_read(conversation)
    return ChatReadResponse(
        conversationId=conversation.id,
        unreadCount=conversation.unread_count,
        unreadTotal=await ChatRepository(db).unread_total(),
    )


@router.post("/chats/{conversation_id}/close", response_model=ChatConversationOut)
async def close_chat(
    conversation_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> ChatConversationOut:
    del manager
    service = ChatService(db)
    try:
        conversation = await service.close_conversation(conversation_id)
    except LookupError as exc:
        raise _not_found("Conversation not found") from exc
    await db.commit()
    payload = await service.conversation_out(conversation)
    await manager_realtime_hub.publish(
        "chat.conversation.updated",
        {"conversation": payload.model_dump(mode="json")},
    )
    return payload


@router.get("/orders", response_model=ManagerOrderListResponse)
async def list_manager_orders(db: DbDep, manager: ManagerUser) -> ManagerOrderListResponse:
    del manager
    repo = OrderRepository(db)
    created = await repo.list_by_status(OrderStatus.CREATED, limit=100)
    processing = await repo.list_by_status(OrderStatus.PROCESSING, limit=100)
    orders = sorted([*created, *processing], key=lambda item: item.createdAt, reverse=True)
    return ManagerOrderListResponse(items=[_manager_order_out(order) for order in orders])


@router.get("/orders/{order_id}", response_model=ManagerOrderSummary)
async def get_manager_order(
    order_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> ManagerOrderSummary:
    del manager
    order = await OrderRepository(db).get_one(order_id)
    if order is None:
        raise _not_found("Order not found")
    return _manager_order_out(order)


@router.post("/orders/{order_id}/chat", response_model=ChatConversationOut)
async def ensure_order_chat(
    order_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> ChatConversationOut:
    del manager
    order = await OrderRepository(db).get_one(order_id)
    if order is None:
        raise _not_found("Order not found")
    repo = ChatRepository(db)
    conversation, created = await repo.get_or_create_conversation(order.UserId)
    if created:
        conversation.user = order.user
    await db.commit()
    return await ChatService(db).conversation_out(conversation)


@router.patch("/orders/{order_id}/status", response_model=ManagerOrderSummary)
async def update_manager_order_status(
    order_id: int,
    body: ManagerOrderStatusRequest,
    db: DbDep,
    manager: ManagerUser,
) -> ManagerOrderSummary:
    del manager
    order = await update_order_status(
        db,
        order_id=order_id,
        status=body.status,
        notify_user=False,
    )
    delivery = await notify_order_status_changed(order, manager_chat_url=None)
    if reconcile_telegram_write_access(
        getattr(order, "user", None),
        delivery,
        operation="manager_workspace_order_status",
    ):
        await db.commit()

    payload = _manager_order_out(order)
    conversation = await ChatRepository(db).get_conversation_by_user(order.UserId)
    await manager_realtime_hub.publish(
        "chat.order.updated",
        {
            "order": payload.model_dump(mode="json"),
            "conversationId": conversation.id if conversation is not None else None,
        },
    )
    return payload


@router.post("/realtime/ticket", response_model=SocketTicketResponse)
async def create_realtime_ticket(manager: ManagerUser) -> SocketTicketResponse:
    ticket = await manager_realtime_hub.issue_ticket(manager.id)
    return SocketTicketResponse(ticket=ticket, expiresInSeconds=SOCKET_TICKET_TTL_SECONDS)


@router.websocket("/realtime/ws")
async def manager_realtime_socket(
    websocket: WebSocket,
    ticket: str = Query(..., min_length=20, max_length=128),
) -> None:
    try:
        manager_id = await manager_realtime_hub.consume_ticket(ticket)
    except Exception:
        await websocket.close(code=1011)
        return
    if manager_id is None:
        await websocket.close(code=4401)
        return

    async with create_db_session() as db:
        manager = await UserRepository(db).get_one(manager_id)
        if manager is None or not has_operator_access(manager.role):
            await websocket.close(code=4403)
            return
        unread_total = await ChatRepository(db).unread_total()

    connection_id = secrets.token_hex(12)
    await websocket.accept()
    try:
        await manager_realtime_hub.register(manager_id, websocket, connection_id)
        await websocket.send_json(
            {
                "type": "realtime.ready",
                "payload": {"unreadTotal": unread_total},
                "managerId": manager_id,
            }
        )
        while True:
            data = await websocket.receive_json()
            await manager_realtime_hub.refresh_presence(manager_id, connection_id)
            event_type = data.get("type")
            if event_type == "ping":
                await websocket.send_json({"type": "realtime.pong", "payload": {}})
                continue
            if event_type == "viewing":
                raw_conversation_id = data.get("conversationId")
                conversation_id = (
                    int(raw_conversation_id) if raw_conversation_id is not None else None
                )
                await manager_realtime_hub.set_viewing(
                    manager_id,
                    connection_id,
                    conversation_id,
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        with suppress(Exception):
            await websocket.close(code=1011)
    finally:
        with suppress(Exception):
            await manager_realtime_hub.unregister(manager_id, websocket, connection_id)
