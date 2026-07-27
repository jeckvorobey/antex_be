"""Add managed marketing platform and currency references.

Revision ID: 021
Revises: 020
Create Date: 2026-07-14 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "MarketingPlatforms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "MarketingCurrencies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.execute(
        "INSERT INTO \"MarketingPlatforms\" (slug, name) VALUES ('telegram_ads', 'Telegram Ads') "
        "ON CONFLICT (slug) DO NOTHING"
    )
    op.execute(
        "INSERT INTO \"MarketingCurrencies\" (code, name) VALUES ('USDT', 'USDT') "
        "ON CONFLICT (code) DO NOTHING"
    )
    op.execute(
        'INSERT INTO "MarketingPlatforms" (slug, name) '
        'SELECT DISTINCT provider, provider FROM "MarketingCampaigns" '
        "ON CONFLICT (slug) DO NOTHING"
    )
    op.execute(
        'INSERT INTO "MarketingCurrencies" (code, name) '
        'SELECT DISTINCT UPPER(currency), UPPER(currency) FROM "MarketingCampaigns" '
        "WHERE currency IS NOT NULL AND currency <> '' ON CONFLICT (code) DO NOTHING"
    )
    op.add_column("MarketingCampaigns", sa.Column("platform_id", sa.Integer(), nullable=True))
    op.add_column("MarketingCampaigns", sa.Column("currency_id", sa.Integer(), nullable=True))
    op.execute(
        'UPDATE "MarketingCampaigns" AS c SET platform_id = p.id '
        'FROM "MarketingPlatforms" AS p WHERE p.slug = c.provider'
    )
    op.execute(
        'UPDATE "MarketingCampaigns" AS c SET currency_id = mc.id '
        'FROM "MarketingCurrencies" AS mc '
        "WHERE mc.code = COALESCE(NULLIF(UPPER(c.currency), ''), 'USDT')"
    )
    op.alter_column("MarketingCampaigns", "platform_id", nullable=False)
    op.alter_column("MarketingCampaigns", "currency_id", nullable=False)
    op.create_foreign_key(
        "fk_marketing_campaign_platform",
        "MarketingCampaigns",
        "MarketingPlatforms",
        ["platform_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_marketing_campaign_currency",
        "MarketingCampaigns",
        "MarketingCurrencies",
        ["currency_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_index("ix_marketing_campaigns_provider_status", table_name="MarketingCampaigns")
    op.create_index(
        "ix_marketing_campaigns_platform_status",
        "MarketingCampaigns",
        ["platform_id", "status"],
    )
    op.drop_column("MarketingCampaigns", "source")
    op.drop_column("MarketingCampaigns", "provider")
    op.drop_column("MarketingCampaigns", "currency")


def downgrade() -> None:
    op.add_column("MarketingCampaigns", sa.Column("currency", sa.String(length=8), nullable=True))
    op.add_column("MarketingCampaigns", sa.Column("provider", sa.String(length=64), nullable=True))
    op.add_column("MarketingCampaigns", sa.Column("source", sa.String(length=128), nullable=True))
    op.execute(
        'UPDATE "MarketingCampaigns" AS c SET provider = p.slug '
        'FROM "MarketingPlatforms" AS p WHERE p.id = c.platform_id'
    )
    op.execute(
        'UPDATE "MarketingCampaigns" AS c SET currency = mc.code '
        'FROM "MarketingCurrencies" AS mc WHERE mc.id = c.currency_id'
    )
    op.alter_column("MarketingCampaigns", "provider", nullable=False)
    op.drop_index("ix_marketing_campaigns_platform_status", table_name="MarketingCampaigns")
    op.create_index(
        "ix_marketing_campaigns_provider_status",
        "MarketingCampaigns",
        ["provider", "status"],
    )
    op.drop_constraint("fk_marketing_campaign_currency", "MarketingCampaigns", type_="foreignkey")
    op.drop_constraint("fk_marketing_campaign_platform", "MarketingCampaigns", type_="foreignkey")
    op.drop_column("MarketingCampaigns", "currency_id")
    op.drop_column("MarketingCampaigns", "platform_id")
    op.drop_table("MarketingCurrencies")
    op.drop_table("MarketingPlatforms")
