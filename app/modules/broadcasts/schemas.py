"""Pydantic-схемы рассылок."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


class BroadcastCreate(BaseModel):
    text: str = Field(min_length=1)
    format: Literal["plain", "html"] = "plain"
    button_text: str | None = None
    button_url: str | None = None
    speed_mode: Literal["free", "paid"] = "free"

    @model_validator(mode="after")
    def validate_button_fields(self) -> BroadcastCreate:
        has_text = bool(self.button_text)
        has_url = bool(self.button_url)
        if has_text != has_url:
            raise ValueError("button_text и button_url должны быть заполнены вместе")
        if self.button_url:
            parsed = urlparse(self.button_url)
            if parsed.scheme not in {"http", "https", "tg"}:
                raise ValueError("button_url должен использовать схему http, https или tg")
            if parsed.scheme in {"http", "https"} and not parsed.netloc:
                raise ValueError("button_url должен быть абсолютным URL")
            if parsed.scheme == "tg" and not parsed.path and not parsed.netloc:
                raise ValueError("button_url со схемой tg должен содержать путь назначения")  # noqa: RUF001
        return self


class BroadcastOut(BaseModel):
    id: int
    status: str
    audience_type: str
    text: str
    format: str
    button_text: str | None
    button_url: str | None
    speed_mode_requested: str
    speed_mode_effective: str
    target_rps: int
    worker_count: int
    total_count: int
    success_count: int
    failed_count: int
    created_by_admin_id: int
    started_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    createdAt: datetime  # noqa: N815
    updatedAt: datetime  # noqa: N815

    model_config = {"from_attributes": True}
