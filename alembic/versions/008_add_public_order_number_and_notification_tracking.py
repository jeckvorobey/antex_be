"""add public order number and notification tracking

Revision ID: 008
Revises: 007
Create Date: 2026-05-22 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "OrderNumberCounters",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("lastValue", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("year"),
    )
    op.add_column("Orders", sa.Column("publicNumber", sa.String(length=10), nullable=True))
    op.add_column("Orders", sa.Column("userNotificationMessageId", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            WITH numbered AS (
                SELECT
                    id,
                    to_char(("createdAt" AT TIME ZONE 'UTC'), 'YYYYMM') ||
                    lpad(
                        row_number() OVER (
                            PARTITION BY extract(year FROM ("createdAt" AT TIME ZONE 'UTC'))
                            ORDER BY "createdAt", id
                        )::text,
                        4,
                        '0'
                    ) AS public_number
                FROM "Orders"
            )
            UPDATE "Orders" AS orders
            SET "publicNumber" = numbered.public_number
            FROM numbered
            WHERE orders.id = numbered.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH yearly_sequence AS (
                SELECT
                    extract(year FROM ("createdAt" AT TIME ZONE 'UTC'))::int AS year,
                    row_number() OVER (
                        PARTITION BY extract(year FROM ("createdAt" AT TIME ZONE 'UTC'))
                        ORDER BY "createdAt", id
                    ) AS seq
                FROM "Orders"
            )
            INSERT INTO "OrderNumberCounters" ("year", "lastValue")
            SELECT year, max(seq)::int AS last_value
            FROM yearly_sequence
            GROUP BY year
            """
        )
    )
    op.alter_column("Orders", "publicNumber", existing_type=sa.String(length=10), nullable=False)
    op.create_unique_constraint("uq_orders_public_number", "Orders", ["publicNumber"])


def downgrade() -> None:
    op.drop_constraint("uq_orders_public_number", "Orders", type_="unique")
    op.drop_column("Orders", "userNotificationMessageId")
    op.drop_column("Orders", "publicNumber")
    op.drop_table("OrderNumberCounters")
