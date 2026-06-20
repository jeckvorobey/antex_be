"""Site lead schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.site_lead import SiteLead


class SiteLeadCreate(BaseModel):
    messenger: str | None = Field(default=None, max_length=50)
    contact: str = Field(min_length=1, max_length=255)
    topic: str | None = Field(default=None, max_length=255)
    message: str = Field(min_length=1, max_length=20_000)
    source: str = Field(default="antex-landing", min_length=1, max_length=100)

    @field_validator("messenger", "contact", "topic", "message", "source", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class SiteLeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    messenger: str | None
    contact: str
    topic: str | None
    message: str
    source: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


def build_site_lead_out(lead: SiteLead) -> SiteLeadOut:
    return SiteLeadOut.model_validate(lead)
