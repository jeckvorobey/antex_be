"""Схемы конфигурации."""
# ruff: noqa: N815

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class AppConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    enabled: bool
    referral_percent: Decimal = Field(alias="referralPercent")
    referral_min_withdraw: Decimal = Field(alias="referralMinWithdraw")
    referral_max_withdraw: Decimal | None = Field(alias="referralMaxWithdraw")
    aex_rate: Decimal = Field(alias="aexRate")
    aex_withdraw_limit: Decimal = Field(alias="aexWithdrawLimit")
    marketing_attribution_window_days: int = Field(alias="marketingAttributionWindowDays")
    manager_schedule_enabled: bool = Field(alias="managerScheduleEnabled")
    manager_working_days_utc: list[int] = Field(alias="managerWorkingDaysUtc")
    manager_start_time_utc: time = Field(alias="managerStartTimeUtc")
    manager_end_time_utc: time = Field(alias="managerEndTimeUtc")
    createdAt: datetime
    updatedAt: datetime

    @field_serializer(
        "referral_percent",
        "referral_min_withdraw",
        "referral_max_withdraw",
        "aex_rate",
        "aex_withdraw_limit",
        when_used="json",
    )
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None
        serialized = format(value, "f")
        if "." in serialized:
            return serialized.rstrip("0").rstrip(".")
        return serialized

    @field_serializer("manager_start_time_utc", "manager_end_time_utc", when_used="json")
    def serialize_manager_time(self, value: time) -> str:
        """Возвращает компактный time-only UTC-контракт без секунд."""
        return value.strftime("%H:%M")


class AppConfigUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    enabled: bool | None = None
    referral_percent: Decimal | None = Field(default=None, alias="referralPercent", ge=0)
    referral_min_withdraw: Decimal | None = Field(default=None, alias="referralMinWithdraw", ge=0)
    referral_max_withdraw: Decimal | None = Field(default=None, alias="referralMaxWithdraw", ge=0)
    aex_rate: Decimal | None = Field(default=None, alias="aexRate", gt=0)
    aex_withdraw_limit: Decimal | None = Field(default=None, alias="aexWithdrawLimit", ge=0)
    marketing_attribution_window_days: int | None = Field(
        default=None,
        alias="marketingAttributionWindowDays",
        ge=1,
        le=90,
    )
    manager_schedule_enabled: bool | None = Field(default=None, alias="managerScheduleEnabled")
    manager_working_days_utc: list[Annotated[int, Field(strict=True, ge=1, le=7)]] | None = Field(
        default=None,
        alias="managerWorkingDaysUtc",
        min_length=1,
        max_length=7,
    )
    manager_start_time_utc: time | None = Field(default=None, alias="managerStartTimeUtc")
    manager_end_time_utc: time | None = Field(default=None, alias="managerEndTimeUtc")

    @field_validator("manager_working_days_utc")
    @classmethod
    def validate_manager_working_days(cls, value: list[int] | None) -> list[int] | None:
        """Запрещает неполные, повторяющиеся и выходящие за ISO-неделю дни в API-контракте."""
        if value is None:
            return value
        if any(day < 1 or day > 7 for day in value):
            raise ValueError("Manager working days must use ISO values from 1 to 7")
        if len(set(value)) != len(value):
            raise ValueError("Manager working days must not contain duplicates")
        return value

    @field_validator("manager_start_time_utc", "manager_end_time_utc")
    @classmethod
    def validate_manager_utc_time(cls, value: time | None) -> time | None:
        """Принимает только time-only UTC: offset был бы проигнорирован планировщиком."""
        if value is not None and value.tzinfo is not None:
            raise ValueError("Manager working time must be a UTC time without an offset")
        if value is not None and (value.second or value.microsecond):
            raise ValueError("Manager working time must use minute precision")
        return value
