"""Разрешить хранение внутренних курсов без раскрытия через API.

Revision ID: 023
Revises: 022
Create Date: 2026-07-20 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет признак внутреннего курса и разрешает отсутствие страны."""
    op.add_column(
        "Rates",
        sa.Column(
            "is_internal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("Rates", "country", existing_type=sa.Enum(name="country_enum"), nullable=True)
    op.execute(
        sa.text(
            """
            WITH ranked_reserved_rates AS (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY upper(currency)
                        ORDER BY (currency = upper(currency)) DESC, id
                    ) AS row_number
                FROM "Rates"
                WHERE upper(currency) IN ('USDTRUB', 'RUBUSDT')
            )
            DELETE FROM "Rates"
            USING ranked_reserved_rates
            WHERE "Rates".id = ranked_reserved_rates.id
              AND ranked_reserved_rates.row_number > 1
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE "Rates"
            SET currency = upper(currency), is_internal = true, country = NULL
            WHERE upper(currency) IN ('USDTRUB', 'RUBUSDT')
            """
        )
    )


def downgrade() -> None:
    """Удаляет внутренние строки и возвращает обязательную страну."""
    op.execute(sa.text('DELETE FROM "Rates" WHERE is_internal = true OR country IS NULL'))
    op.alter_column("Rates", "country", existing_type=sa.Enum(name="country_enum"), nullable=False)
    op.drop_column("Rates", "is_internal")
