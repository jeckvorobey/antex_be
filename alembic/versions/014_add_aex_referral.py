"""Add ATXG referral system tables.

Revision ID: 014
Revises: 013
Create Date: 2026-06-24 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавить поля реферальной системы к Users
    op.add_column(
        "Users",
        sa.Column("referral_code", sa.String(16), unique=True, nullable=True),
    )
    op.add_column(
        "Users",
        sa.Column("referred_by", sa.Integer, sa.ForeignKey("Users.id"), nullable=True),
    )

    # Создать таблицу AexWallets
    op.create_table(
        "AexWallets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("Users.id"), unique=True, nullable=False),
        sa.Column(
            "balance_available",
            sa.Numeric(precision=18, scale=8),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "balance_reserved",
            sa.Numeric(precision=18, scale=8),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Создать таблицу AexLedgerEntries
    op.create_table(
        "AexLedgerEntries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "wallet_id",
            sa.Integer,
            sa.ForeignKey("AexWallets.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("entry_type", sa.String(20), nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("reference_id", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Создать таблицу AexRates
    op.create_table(
        "AexRates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "global_rate",
            sa.Numeric(precision=10, scale=6),
            server_default="0.002",
            nullable=False,
        ),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Создать таблицу AexPersonalRates
    op.create_table(
        "AexPersonalRates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("Users.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("rate", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("AexPersonalRates")
    op.drop_table("AexRates")
    op.drop_table("AexLedgerEntries")
    op.drop_table("AexWallets")
    op.drop_column("Users", "referred_by")
    op.drop_column("Users", "referral_code")
