"""Add marketing campaign management tables.

Revision ID: 014
Revises: 013
Create Date: 2026-07-13 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "MarketingCampaigns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("medium", sa.String(length=128), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("objective", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("budget", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("starts_at", sa.Date(), nullable=True),
        sa.Column("ends_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("budget IS NULL OR budget >= 0", name="ck_marketing_campaign_budget"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_marketing_campaigns_provider_status",
        "MarketingCampaigns",
        ["provider", "status"],
    )
    op.create_table(
        "MarketingAttributions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column(
            "attributed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["MarketingCampaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["Users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_marketing_attributions_campaign_attributed",
        "MarketingAttributions",
        ["campaign_id", "attributed_at"],
    )
    op.create_table(
        "MarketingDailyMetrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("starts", sa.Integer(), nullable=False),
        sa.Column("spend", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("platform_cpm", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column(
            "createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("impressions >= 0", name="ck_marketing_daily_impressions"),
        sa.CheckConstraint("starts >= 0", name="ck_marketing_daily_starts"),
        sa.CheckConstraint("spend >= 0", name="ck_marketing_daily_spend"),
        sa.CheckConstraint(
            "platform_cpm IS NULL OR platform_cpm >= 0",
            name="ck_marketing_daily_platform_cpm",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["MarketingCampaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "metric_date", name="uq_marketing_daily_campaign_date"),
    )
    op.create_index(
        "ix_marketing_daily_metric_date",
        "MarketingDailyMetrics",
        ["metric_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_marketing_daily_metric_date", table_name="MarketingDailyMetrics")
    op.drop_table("MarketingDailyMetrics")
    op.drop_index(
        "ix_marketing_attributions_campaign_attributed",
        table_name="MarketingAttributions",
    )
    op.drop_table("MarketingAttributions")
    op.drop_index("ix_marketing_campaigns_provider_status", table_name="MarketingCampaigns")
    op.drop_table("MarketingCampaigns")
