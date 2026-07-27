"""Add immutable acquisition, marketing touches and order attribution snapshots.

Revision ID: 024
Revises: 023
"""
# ruff: noqa: E501

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "Configs",
        sa.Column(
            "marketing_attribution_window_days", sa.Integer(), server_default="7", nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_config_marketing_attribution_window",
        "Configs",
        "marketing_attribution_window_days BETWEEN 1 AND 90",
    )
    op.create_table(
        "UserAcquisitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("referrer_user_id", sa.Integer()),
        sa.Column("campaign_id", sa.Integer()),
        sa.Column(
            "acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["Users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["Users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["campaign_id"], ["MarketingCampaigns.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "source_type IN ('referral', 'campaign', 'direct', 'legacy')",
            name="ck_user_acquisition_source",
        ),
        sa.CheckConstraint(
            "(source_type = 'referral') = (referrer_user_id IS NOT NULL)",
            name="ck_user_acquisition_referrer",
        ),
        sa.CheckConstraint(
            "(source_type = 'campaign') = (campaign_id IS NOT NULL)",
            name="ck_user_acquisition_campaign",
        ),
    )
    op.create_index(
        "ix_user_acquisitions_campaign_acquired",
        "UserAcquisitions",
        ["campaign_id", "acquired_at"],
    )
    op.create_table(
        "MarketingTouches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column(
            "touched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("user_state", sa.String(16), nullable=False),
        sa.Column("session_key", sa.String(128)),
        sa.Column("metadata", sa.JSON()),
        sa.ForeignKeyConstraint(["user_id"], ["Users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["MarketingCampaigns.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "user_state IN ('new', 'returning')", name="ck_marketing_touch_user_state"
        ),
        sa.UniqueConstraint(
            "user_id", "campaign_id", "session_key", name="uq_marketing_touch_session"
        ),
    )
    op.create_index(
        "ix_marketing_touches_user_touched", "MarketingTouches", ["user_id", "touched_at"]
    )
    op.create_index("ix_orders_user_id", "Orders", ["UserId"])
    op.create_index(
        "ix_marketing_touches_campaign_touched", "MarketingTouches", ["campaign_id", "touched_at"]
    )
    op.create_table(
        "OrderAttributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("campaign_id", sa.Integer()),
        sa.Column("marketing_touch_id", sa.Integer()),
        sa.Column("attribution_type", sa.String(16), nullable=False),
        sa.Column("attributed_at", sa.DateTime(timezone=True)),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["Orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["MarketingCampaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["marketing_touch_id"], ["MarketingTouches.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "attribution_type IN ('acquisition', 'reengagement', 'none')",
            name="ck_order_attribution_type",
        ),
        sa.CheckConstraint(
            "(attribution_type = 'none') = (campaign_id IS NULL)",
            name="ck_order_attribution_campaign",
        ),
        sa.CheckConstraint(
            "(attribution_type = 'none') = (marketing_touch_id IS NULL)",
            name="ck_order_attribution_touch",
        ),
        sa.CheckConstraint("lookback_days BETWEEN 1 AND 90", name="ck_order_attribution_lookback"),
    )
    op.create_index(
        "ix_order_attributions_campaign_attributed",
        "OrderAttributions",
        ["campaign_id", "attributed_at"],
    )
    op.create_table(
        "AttributionAuditEvents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer()),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(16)),
        sa.Column("referrer_user_id", sa.Integer()),
        sa.Column("campaign_id", sa.Integer()),
        sa.Column("reason", sa.String(128)),
        sa.Column(
            "createdAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updatedAt", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["Users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["Users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["MarketingCampaigns.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_attribution_audit_user_created", "AttributionAuditEvents", ["user_id", "createdAt"]
    )
    op.execute(
        'INSERT INTO "UserAcquisitions" (user_id, source_type, acquired_at) SELECT id, \'legacy\', "createdAt" FROM "Users" ON CONFLICT (user_id) DO NOTHING'
    )
    # Legacy rows came only from trusted Telegram auth, so they prove a campaign touch,
    # but not whether the user was new. Preserve them conservatively as returning touches;
    # never derive a campaign acquisition or `new` user_state from this table.
    op.execute(
        'INSERT INTO "MarketingTouches" (user_id, campaign_id, touched_at, user_state, metadata) SELECT legacy.user_id, legacy.campaign_id, legacy.attributed_at, \'returning\', \'{"source":"legacy_trusted_telegram_auth"}\'::json FROM "MarketingAttributions" legacy WHERE NOT EXISTS (SELECT 1 FROM "MarketingTouches" touch WHERE touch.user_id = legacy.user_id AND touch.campaign_id = legacy.campaign_id AND touch.touched_at = legacy.attributed_at AND touch.metadata->>\'source\' = \'legacy_trusted_telegram_auth\')'
    )
    op.execute(
        'INSERT INTO "OrderAttributions" (order_id, campaign_id, marketing_touch_id, attribution_type, attributed_at, lookback_days) SELECT orders.id, touches.campaign_id, touches.id, \'reengagement\', touches.touched_at, 7 FROM "Orders" orders JOIN "MarketingTouches" touches ON touches.user_id = orders."UserId" AND touches.metadata->>\'source\' = \'legacy_trusted_telegram_auth\' WHERE orders."createdAt" >= touches.touched_at AND orders."createdAt" <= touches.touched_at + interval \'7 days\' ON CONFLICT (order_id) DO NOTHING'
    )
    op.execute(
        'INSERT INTO "OrderAttributions" (order_id, attribution_type, lookback_days) SELECT id, \'none\', 7 FROM "Orders" ON CONFLICT (order_id) DO NOTHING'
    )


def downgrade() -> None:
    raise RuntimeError("024 attribution data is forward-only; use a corrective migration")
