"""Add unique referral ledger reference index.

Revision ID: 016
Revises: 015
Create Date: 2026-06-26 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TEMP TABLE duplicate_referral_credits ON COMMIT DROP AS
        SELECT id, wallet_id, amount, reference_id
        FROM (
            SELECT
                id,
                wallet_id,
                amount,
                reference_id,
                row_number() OVER (
                    PARTITION BY reference_id
                    ORDER BY id
                ) AS duplicate_number
            FROM "AexLedgerEntries"
            WHERE reference_type = 'referral'
              AND entry_type = 'credit'
              AND reference_id IS NOT NULL
        ) ranked_referrals
        WHERE duplicate_number > 1
        """
    )
    op.execute(
        """
        INSERT INTO "AexLedgerEntries" (
            wallet_id,
            amount,
            entry_type,
            reference_type,
            reference_id,
            description,
            "createdAt",
            "updatedAt"
        )
        SELECT
            wallet_id,
            -amount,
            'debit',
            'referral_duplicate_cleanup',
            reference_id,
            'Correction for duplicate referral credit before unique index',
            now(),
            now()
        FROM duplicate_referral_credits
        """
    )
    op.execute(
        """
        UPDATE "AexWallets" wallet
        SET
            balance_available = wallet.balance_available - duplicate_totals.amount,
            "updatedAt" = now()
        FROM (
            SELECT wallet_id, sum(amount) AS amount
            FROM duplicate_referral_credits
            GROUP BY wallet_id
        ) duplicate_totals
        WHERE wallet.id = duplicate_totals.wallet_id
        """
    )
    op.execute(
        """
        UPDATE "AexLedgerEntries" ledger
        SET
            reference_type = 'referral_duplicate',
            description = concat_ws(
                E'\n',
                NULLIF(ledger.description, ''),
                'Duplicate referral credit excluded before unique index'
            ),
            "updatedAt" = now()
        FROM duplicate_referral_credits duplicates
        WHERE ledger.id = duplicates.id
        """
    )
    op.create_index(
        "uq_aex_ledger_referral_reference",
        "AexLedgerEntries",
        ["reference_type", "reference_id"],
        unique=True,
        postgresql_where=sa.text("reference_type = 'referral'"),
        sqlite_where=sa.text("reference_type = 'referral'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_aex_ledger_referral_reference",
        table_name="AexLedgerEntries",
    )
