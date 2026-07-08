"""Add unique ATXG withdraw ledger reference index.

Revision ID: 019
Revises: 018
Create Date: 2026-07-07 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


WITHDRAW_REFERENCE_TYPES = (
    "order_withdraw_hold",
    "order_withdraw_debit",
    "order_withdraw_release",
)


def _reference_filter() -> sa.TextClause:
    quoted = ", ".join(f"'{item}'" for item in WITHDRAW_REFERENCE_TYPES)
    return sa.text(f"reference_type IN ({quoted})")


def upgrade() -> None:
    op.create_index(
        "uq_aex_ledger_order_withdraw_reference",
        "AexLedgerEntries",
        ["reference_type", "reference_id"],
        unique=True,
        postgresql_where=_reference_filter(),
        sqlite_where=_reference_filter(),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_aex_ledger_order_withdraw_reference",
        table_name="AexLedgerEntries",
    )
