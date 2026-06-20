"""reshape orders for country aware flow

Revision ID: 007
Revises: 006
Create Date: 2026-05-18 00:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "007"
down_revision = "006"
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
    op.alter_column("Orders", "CityId", existing_type=sa.Integer(), nullable=True)
    op.add_column("Orders", sa.Column("country", COUNTRY_ENUM, nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE "Orders" AS o
            SET country = c.country
            FROM "Cities" AS c
            WHERE o."CityId" = c.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE "Orders"
            SET status = CASE
                WHEN status IN (2, 3) THEN 2
                WHEN status = 4 THEN 3
                WHEN status = 5 THEN 4
                ELSE 1
            END
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE "Orders"
            SET "methodGet" = CASE
                WHEN lower(coalesce("methodGet", '')) IN ('qr', 'qrcode') THEN 'qrcode'
                ELSE 'cash'
            END
            """
        )
    )
    op.alter_column("Orders", "country", nullable=False)
    op.alter_column("Orders", "methodGet", existing_type=sa.String(length=20), nullable=False)
    op.drop_column("Orders", "address")


def downgrade() -> None:
    op.add_column("Orders", sa.Column("address", sa.String(length=255), nullable=True))
    op.alter_column("Orders", "methodGet", existing_type=sa.String(length=20), nullable=True)
    op.drop_column("Orders", "country")
    op.alter_column("Orders", "CityId", existing_type=sa.Integer(), nullable=False)
