"""Store fractional exchange sell amounts.

Revision ID: 042
Revises: 041
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "Orders",
        "amountSell",
        existing_type=sa.Integer(),
        type_=sa.Numeric(precision=20, scale=8),
        existing_nullable=False,
        postgresql_using='"amountSell"::numeric(20, 8)',
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM "Orders" WHERE "amountSell" <> trunc("amountSell")
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade Orders.amountSell while fractional values exist';
            END IF;
        END $$;
        """
    )
    op.alter_column(
        "Orders",
        "amountSell",
        existing_type=sa.Numeric(precision=20, scale=8),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using='"amountSell"::integer',
    )
