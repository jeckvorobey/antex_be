"""Operational API and WebSocket for the Mini App manager workspace."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime

from app.api.deps import DbDep, ManagerUser
from app.core.config import settings
from app.core.database import create_db_session
from app.repositories.chat import ChatRepository
from app.repositories.order import OrderRepository
from app.schemas.chat import (
    ChatConversationOut,
    ChatForwardRequest,
    ChatListResponse,
    ChatMessageOut,
    ChatMessagesResponse,
    ChatReadResponse,
    ChatSendRequest,
    ManagerOrderListResponse,
    ManagerOrderStatusRequest,
    ManagerOrderSummary,
    ManagerRealtimeViewingRequest,
)
from app.services.chat import ChatService
from app.services.chat_forwarding import forward_manager_message
from app.services.chat_realtime import manager_realtime_hub, trigger_manager_refresh
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
    repo = ChatRepository(db, manager_id=manager.id)
    service = ChatService(db, manager_id=manager.id)
    conversations, total = await repo.list_conversations(
        unread_only=unreadOnly,
        query=query,
        limit=limit,
        offset=offset,
    )
    items = await service.conversations_out(conversations)
    return ChatListResponse(items=items, total=total, unreadTotal=await repo.unread_total())


@router.get("/chats/{conversation_id}", response_model=ChatConversationOut)
async def get_chat(
    conversation_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> ChatConversationOut:
    conversation = await ChatRepository(db, manager_id=manager.id).get_conversation(conversation_id)
    if conversation is None:
        raise _not_found("Conversation not found")
    return await ChatService(db, manager_id=manager.id).conversation_out(conversation)


@router.get("/chats/{conversation_id}/messages", response_model=ChatMessagesResponse)
async def get_chat_messages(
    conversation_id: int,
    db: DbDep,
    manager: ManagerUser,
    limit: int = Query(50, ge=1, le=100),
    beforeId: int | None = Query(None, ge=1),  # noqa: N803
) -> ChatMessagesResponse:
    repo = ChatRepository(db, manager_id=manager.id)
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
    service = ChatService(db, manager_id=manager.id)
    try:
        message, conversation, created = await service.send_manager_message(
            conversation_id=conversation_id,
            client_request_id=body.clientRequestId,
            text=body.text,
            reply_to_message_id=body.replyToMessageId,
        )
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    if created:
        await service.publish_outbound(message, conversation)
    return service.message_out(message)


@router.post("/chats/{conversation_id}/forward", response_model=ChatMessageOut)
async def forward_chat_message(
    conversation_id: int,
    body: ChatForwardRequest,
    db: DbDep,
    manager: ManagerUser,
) -> ChatMessageOut:
    """Переслать доступное сообщение нативным методом Telegram."""
    try:
        message, conversation, attempted = await forward_manager_message(
            db,
            manager_id=manager.id,
            conversation_id=conversation_id,
            client_request_id=body.clientRequestId,
            source_message_id=body.sourceMessageId,
        )
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    service = ChatService(db, manager_id=manager.id)
    if attempted:
        await service.publish_outbound(message, conversation)
    return service.message_out(message)


@router.post("/chats/{conversation_id}/read", response_model=ChatReadResponse)
async def mark_chat_read(
    conversation_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> ChatReadResponse:
    service = ChatService(db, manager_id=manager.id)
    try:
        conversation = await service.mark_read(conversation_id)
    except LookupError as exc:
        raise _not_found("Conversation not found") from exc
    await db.commit()
    await service.publish_read(conversation)
    return ChatReadResponse(
        conversationId=conversation.id,
        unreadCount=conversation.unread_count,
        unreadTotal=await ChatRepository(db, manager_id=manager.id).unread_total(),
    )


@router.post("/chats/{conversation_id}/close", response_model=ChatConversationOut)
async def close_chat(
    conversation_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> ChatConversationOut:
    service = ChatService(db, manager_id=manager.id)
    try:
        conversation = await service.close_conversation(conversation_id)
    except LookupError as exc:
        raise _not_found("Conversation not found") from exc
    await db.commit()
    payload = await service.conversation_out(conversation)
    await manager_realtime_hub.publish(
        "chat.conversation.updated",
        {"conversation": payload.model_dump(mode="json")},
        manager_id=manager.id,
    )
    return payload


@router.get("/orders", response_model=ManagerOrderListResponse)
async def list_manager_orders(
    db: DbDep,
    manager: ManagerUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    todayFrom: Annotated[AwareDatetime | None, Query()] = None,  # noqa: N803
) -> ManagerOrderListResponse:
    today_from = (
        todayFrom.astimezone(UTC)
        if todayFrom is not None
        else datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    )
    orders, total, today_total, amounts = await OrderRepository(db).manager_page(
        limit=limit,
        offset=offset,
        today_from=today_from,
    )
    return ManagerOrderListResponse(
        items=[_manager_order_out(order) for order in orders],
        total=total,
        todayTotal=today_total,
        amountTotals=amounts,
    )


@router.get("/orders/{order_id}", response_model=ManagerOrderSummary)
async def get_manager_order(
    order_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> ManagerOrderSummary:
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
    order = await OrderRepository(db).get_one(order_id)
    if order is None:
        raise _not_found("Order not found")
    repo = ChatRepository(db, manager_id=manager.id)
    conversation, created = await repo.get_or_create_conversation(order.UserId)
    if created:
        conversation.user = order.user
    await db.commit()
    return await ChatService(db, manager_id=manager.id).conversation_out(conversation)


@router.patch("/orders/{order_id}/status", response_model=ManagerOrderSummary)
async def update_manager_order_status(
    order_id: int,
    body: ManagerOrderStatusRequest,
    db: DbDep,
    manager: ManagerUser,
) -> ManagerOrderSummary:
    order = await update_order_status(
        db,
        order_id=order_id,
        status=body.status,
        manager_id=manager.id,
    )

    payload = _manager_order_out(order)
    await trigger_manager_refresh(manager, "order.status.updated")
    return payload


def _sse_event(envelope: dict[str, object]) -> str:
    return f"event: {envelope['type']}\ndata: {json.dumps(envelope, default=str)}\n\n"


@router.get("/realtime/stream")
async def manager_realtime_stream(
    manager: ManagerUser,
    connection_id: str = Header(..., alias="X-Manager-Realtime-Connection-Id"),
) -> StreamingResponse:
    try:
        UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid connection id"
        ) from exc
    async with create_db_session() as db:
        unread_total = await ChatRepository(db, manager_id=manager.id).unread_total()

    async def events():
        connection = await manager_realtime_hub.register(manager.id, connection_id)
        try:
            yield _sse_event(
                {
                    "type": "realtime.ready",
                    "payload": {"unreadTotal": unread_total},
                    "managerId": manager.id,
                }
            )
            while True:
                try:
                    envelope = await asyncio.wait_for(
                        connection.events.get(), timeout=settings.manager_realtime_keepalive_seconds
                    )
                except TimeoutError:
                    await manager_realtime_hub.refresh_presence(manager.id, connection_id)
                    yield ": keepalive\n\n"
                else:
                    yield _sse_event(envelope)
        finally:
            with suppress(Exception):
                await manager_realtime_hub.unregister(manager.id, connection_id)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.put("/realtime/viewing", status_code=status.HTTP_204_NO_CONTENT)
async def update_realtime_viewing(
    body: ManagerRealtimeViewingRequest,
    manager: ManagerUser,
    db: DbDep,
) -> Response:
    """Сохраняет viewing только собственной беседы менеджера."""
    if body.conversationId is not None:
        conversation = await ChatRepository(db, manager_id=manager.id).get_conversation(
            body.conversationId
        )
        if conversation is None:
            raise _not_found("Conversation not found")
    if not await manager_realtime_hub.set_viewing(
        manager.id, body.connectionId, body.conversationId
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Realtime connection is not active"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
