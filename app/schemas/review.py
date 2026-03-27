"""Схемы отзывов."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ReviewCreate(BaseModel):
    OrderId: int
    text: str
    fromChatId: int
    msgId: int
    anonymous: bool = False


class ReviewOut(BaseModel):
    id: int
    OrderId: int
    text: str
    fromChatId: int
    msgId: int
    publish: bool
    anonymous: bool
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}
