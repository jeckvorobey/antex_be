"""Pydantic-контракты marketing Admin API."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.marketing.constants import (
    DEFAULT_MARKETING_PROVIDER,
    MARKETING_CAMPAIGN_STATUSES,
    MARKETING_PROVIDERS,
)


class MarketingSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CampaignCreate(MarketingSchema):
    name: str = Field(min_length=1, max_length=255)
    provider: str = DEFAULT_MARKETING_PROVIDER
    source: str | None = Field(default=None, max_length=128)
    medium: str | None = Field(default=None, max_length=128)
    external_id: str | None = Field(default=None, alias="externalId", max_length=255)
    objective: str | None = Field(default=None, max_length=255)
    status: str = "draft"
    budget: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    starts_at: date | None = Field(default=None, alias="startsAt")
    ends_at: date | None = Field(default=None, alias="endsAt")
    notes: str | None = None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if value not in MARKETING_PROVIDERS:
            raise ValueError("Unsupported marketing provider")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in MARKETING_CAMPAIGN_STATUSES:
            raise ValueError("Unsupported campaign status")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @model_validator(mode="after")
    def validate_dates(self) -> CampaignCreate:
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("endsAt must not be earlier than startsAt")
        if self.budget is not None and self.currency is None:
            raise ValueError("currency is required when budget is set")
        return self


class CampaignUpdate(MarketingSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=128)
    medium: str | None = Field(default=None, max_length=128)
    external_id: str | None = Field(default=None, alias="externalId", max_length=255)
    objective: str | None = Field(default=None, max_length=255)
    status: str | None = None
    budget: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    starts_at: date | None = Field(default=None, alias="startsAt")
    ends_at: date | None = Field(default=None, alias="endsAt")
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in MARKETING_CAMPAIGN_STATUSES:
            raise ValueError("Unsupported campaign status")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class CampaignOut(MarketingSchema):
    id: int
    code: str
    name: str
    provider: str
    source: str | None
    medium: str | None
    external_id: str | None = Field(alias="externalId")
    objective: str | None
    status: str
    budget: float | None
    currency: str | None
    starts_at: date | None = Field(alias="startsAt")
    ends_at: date | None = Field(alias="endsAt")
    notes: str | None
    link: str
    market_parameter: str = Field(alias="marketParameter")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    attributed_users: int = Field(default=0, alias="attributedUsers")
    applications: int = 0


class CampaignListOut(MarketingSchema):
    items: list[CampaignOut]
    total: int
    limit: int
    offset: int


class DailyMetricUpsert(MarketingSchema):
    impressions: int = Field(ge=0)
    starts: int = Field(ge=0)
    spend: float = Field(ge=0)
    platform_cpm: float | None = Field(default=None, alias="platformCpm", ge=0)


class DailyMetricOut(MarketingSchema):
    id: int
    campaign_id: int = Field(alias="campaignId")
    metric_date: date = Field(alias="metricDate")
    impressions: int
    starts: int
    spend: float
    platform_cpm: float | None = Field(alias="platformCpm")


class ApplicationRowOut(MarketingSchema):
    campaign_id: int = Field(alias="campaignId")
    campaign_name: str = Field(alias="campaignName")
    code: str
    provider: str
    status: str
    currency: str | None
    attributed_users: int = Field(alias="attributedUsers")
    applications: int
    unique_applicants: int = Field(alias="uniqueApplicants")
    completed_applications: int = Field(alias="completedApplications")
    attribution_to_application_rate: float | None = Field(alias="attributionToApplicationRate")
    application_completion_rate: float | None = Field(alias="applicationCompletionRate")
    spend: float
    cost_per_application: float | None = Field(alias="costPerApplication")


class ApplicationListOut(MarketingSchema):
    items: list[ApplicationRowOut]
    total: int
    limit: int
    offset: int
    applied_filters: dict[str, object | None] = Field(alias="appliedFilters")


class DashboardOut(MarketingSchema):
    summary: dict[str, object]
    funnel: list[dict[str, object]]
    time_series: list[dict[str, object]] = Field(alias="timeSeries")
    campaign_comparison: list[ApplicationRowOut] = Field(alias="campaignComparison")
    spend_by_currency: list[dict[str, object]] = Field(alias="spendByCurrency")
    applied_filters: dict[str, object | None] = Field(alias="appliedFilters")
