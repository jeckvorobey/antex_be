"""API schemas for the manager chat workspace."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.enums.country import Country


class ManagerChatUser(BaseModel):
    id: int
    telegramId: int | None
    username: str | None
    firstName: str | None
    lastName: str | None
    photoUrl: str | None


class ManagerOrderCity(BaseModel):
    id: int
    name: str
    country: Country
    countryRuName: str
    countryCode: str
    countryFlag: str


class ManagerOrderSummary(BaseModel):
    id: int
    publicNumber: str
    currencySell: str
    amountSell: int
    currencyBuy: str
    amountBuy: float | None
    rate: float | None
    rateDisplay: str | None
    rateText: str | None
    country: Country
    city: ManagerOrderCity | None = None
    status: int
    methodGet: str
    createdAt: datetime
    user: ManagerChatUser | None = None


class ChatAttachmentOut(BaseModel):
    id: int
    kind: str
    fileId: str | None
    fileUniqueId: str | None
    filename: str | None
    mimeType: str | None
    size: int | None
    metadata: dict[str, object] = Field(default_factory=dict)


class ChatMessageOut(BaseModel):
    id: int
    conversationId: int
    direction: Literal["inbound", "outbound"]
    messageType: str
    text: str | None
    caption: str | None
    deliveryStatus: str
    telegramMessageId: int | None
    replyToMessageId: int | None
    edited: bool
    createdAt: datetime
    updatedAt: datetime
    attachments: list[ChatAttachmentOut]


class ChatConversationOut(BaseModel):
    id: int
    status: str
    unreadCount: int
    lastMessageAt: datetime | None
    user: ManagerChatUser
    lastMessage: ChatMessageOut | None = None
    latestOrder: ManagerOrderSummary | None = None


class ChatListResponse(BaseModel):
    items: list[ChatConversationOut]
    total: int
    unreadTotal: int


class ChatMessagesResponse(BaseModel):
    items: list[ChatMessageOut]
    hasMore: bool


class ChatSendRequest(BaseModel):
    clientRequestId: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=4096)
    replyToMessageId: int | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message text must not be blank")
        return value


class ChatReadResponse(BaseModel):
    conversationId: int
    unreadCount: int
    unreadTotal: int


class SocketTicketResponse(BaseModel):
    ticket: str
    expiresInSeconds: int


class ManagerOrderListResponse(BaseModel):
    items: list[ManagerOrderSummary]


class ManagerOrderStatusRequest(BaseModel):
    status: int = Field(ge=1, le=4)


class RealtimeEnvelope(BaseModel):
    type: str
    payload: dict[str, object]
