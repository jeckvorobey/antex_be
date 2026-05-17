"""Add country ownership to rates.

Revision ID: 005
Revises: 004
Create Date: 2026-05-17 00:10:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


COUNTRY_ENUM = postgresql.ENUM(
    "thailand",
    "vietnam",
    "georgia",
    name="country_enum",
    create_type=False,
)


def upgrade() -> None:
    migration_context = op.get_context()
    with migration_context.autocommit_block():
        op.execute("ALTER TYPE country_enum ADD VALUE IF NOT EXISTS 'georgia'")
    op.add_column(
        "Rates",
        sa.Column(
            "country",
            COUNTRY_ENUM,
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE "Rates"
            SET country = CASE
                WHEN upper(currency) LIKE '%THB' THEN 'thailand'::country_enum
                WHEN upper(currency) LIKE '%VND' THEN 'vietnam'::country_enum
                WHEN upper(currency) LIKE '%GEL' THEN 'georgia'::country_enum
                ELSE NULL
            END
            """
        )
    )
    op.alter_column("Rates", "country", nullable=False)


def downgrade() -> None:
    op.drop_column("Rates", "country")
