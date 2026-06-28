"""Схемы конфигурации."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class AppConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    enabled: bool
    referral_percent: Decimal = Field(alias="referralPercent")
    referral_min_withdraw: Decimal = Field(alias="referralMinWithdraw")
    referral_max_withdraw: Decimal | None = Field(alias="referralMaxWithdraw")
    aex_rate: Decimal = Field(alias="aexRate")
    createdAt: datetime
    updatedAt: datetime

    @field_serializer(
        "referral_percent",
        "referral_min_withdraw",
        "referral_max_withdraw",
        "aex_rate",
        when_used="json",
    )
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        serialized = format(value, "f")
        if "." in serialized:
            return serialized.rstrip("0").rstrip(".")
        return serialized


class AppConfigUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    enabled: bool | None = None
    referral_percent: Decimal | None = Field(default=None, alias="referralPercent", ge=0)
    referral_min_withdraw: Decimal | None = Field(default=None, alias="referralMinWithdraw", ge=0)
    referral_max_withdraw: Decimal | None = Field(default=None, alias="referralMaxWithdraw", ge=0)
    aex_rate: Decimal | None = Field(default=None, alias="aexRate", gt=0)
