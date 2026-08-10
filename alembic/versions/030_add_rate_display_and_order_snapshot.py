"""Добавить настройку показа курса и снимок представления заявки.

Revision ID: 030
Revises: 029
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None

_REVERSED_PAIRS = "'RUBTHB', 'RUBGEL', 'RUBUSDT'"


def upgrade() -> None:
    """Переносит ориентацию курса в данные и фиксирует её в заявках."""
    op.add_column(
        "Rates",
        sa.Column(
            "display_reversed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            f'UPDATE "Rates" SET display_reversed = true '
            f"WHERE upper(currency) IN ({_REVERSED_PAIRS})"
        )
    )

    op.add_column("Orders", sa.Column("displayRate", sa.Float(), nullable=True))
    op.add_column("Orders", sa.Column("displayCurrencySell", sa.String(20), nullable=True))
    op.add_column("Orders", sa.Column("displayCurrencyBuy", sa.String(20), nullable=True))
    op.execute(
        sa.text(
            f"""
            UPDATE "Orders"
            SET
                "displayRate" = CASE
                    WHEN upper("currencySell" || "currencyBuy") IN ({_REVERSED_PAIRS})
                        AND rate <> 0
                    THEN 1 / rate
                    ELSE rate
                END,
                "displayCurrencySell" = CASE
                    WHEN upper("currencySell" || "currencyBuy") IN ({_REVERSED_PAIRS})
                    THEN upper("currencyBuy")
                    ELSE upper("currencySell")
                END,
                "displayCurrencyBuy" = CASE
                    WHEN upper("currencySell" || "currencyBuy") IN ({_REVERSED_PAIRS})
                    THEN upper("currencySell")
                    ELSE upper("currencyBuy")
                END
            WHERE rate IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    """Удаляет снимок представления и настройку ориентации курса."""
    op.drop_column("Orders", "displayCurrencyBuy")
    op.drop_column("Orders", "displayCurrencySell")
    op.drop_column("Orders", "displayRate")
    op.drop_column("Rates", "display_reversed")
