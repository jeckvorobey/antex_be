"""Pydantic-контракты marketing Admin API."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.marketing.constants import MARKETING_CAMPAIGN_STATUSES


class MarketingSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CampaignCreate(MarketingSchema):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=64)
    external_id: str | None = Field(default=None, alias="externalId", max_length=255)
    objective: str | None = Field(default=None, max_length=255)
    status: str = "draft"
    budget: float | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=8)
    starts_at: date | None = Field(default=None, alias="startsAt")
    ends_at: date | None = Field(default=None, alias="endsAt")
    notes: str | None = None

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in MARKETING_CAMPAIGN_STATUSES:
            raise ValueError("Unsupported campaign status")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_dates(self) -> CampaignCreate:
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("endsAt must not be earlier than startsAt")
        return self


class CampaignUpdate(MarketingSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
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
    external_id: str | None = Field(alias="externalId")
    objective: str | None
    status: str
    budget: float | None
    currency: str
    starts_at: date | None = Field(alias="startsAt")
    ends_at: date | None = Field(alias="endsAt")
    notes: str | None
    link: str
    market_parameter: str = Field(alias="marketParameter")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    attributed_users: int = Field(default=0, alias="attributedUsers")
    applications: int = 0
    campaign_type: str = Field(alias="campaignType")


class MarketingPlatformCreate(MarketingSchema):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=128)

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class MarketingPlatformOut(MarketingSchema):
    slug: str
    name: str


class MarketingCurrencyCreate(MarketingSchema):
    code: str = Field(min_length=3, max_length=8, pattern=r"^[A-Za-z0-9]+$")
    name: str = Field(min_length=1, max_length=64)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class MarketingCurrencyOut(MarketingSchema):
    code: str
    name: str


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
