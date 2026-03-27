"""Initial migration — все таблицы AntEx.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "Users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("language_code", sa.String(10), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("session", sa.Text(), nullable=True),
        sa.Column("chatId", sa.BigInteger(), nullable=True),
        sa.Column("role", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Banks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "Cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bank", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("number", sa.String(255), nullable=False),
        sa.Column("isActive", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("UserId", sa.BigInteger(), nullable=False),
        sa.Column("BankId", sa.Integer(), nullable=False),
        sa.Column("CardId", sa.Integer(), nullable=True),
        sa.Column("currencySell", sa.String(20), nullable=False),
        sa.Column("amountSell", sa.Integer(), nullable=False),
        sa.Column("currencyBuy", sa.String(20), nullable=False),
        sa.Column("amountBuy", sa.Integer(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("methodGet", sa.String(20), nullable=True),
        sa.Column("endTime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("destroyTime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["UserId"], ["Users.id"]),
        sa.ForeignKeyConstraint(["BankId"], ["Banks.id"]),
        sa.ForeignKeyConstraint(["CardId"], ["Cards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "BankAccounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("BankId", sa.Integer(), nullable=False),
        sa.Column("OrderId", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(255), nullable=False),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["BankId"], ["Banks.id"]),
        sa.ForeignKeyConstraint(["OrderId"], ["Orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(20), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("currency"),
    )

    op.create_table(
        "Limitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("BankId", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="50000"),
        sa.Column("baseAmount", sa.Integer(), nullable=False, server_default="50000"),
        sa.Column("icon", sa.String(255), nullable=True),
        sa.Column("isActive", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["BankId"], ["Banks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("OrderId", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("fromChatId", sa.BigInteger(), nullable=False),
        sa.Column("msgId", sa.Integer(), nullable=False),
        sa.Column("publish", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("anonymous", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["OrderId"], ["Orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Allowances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("UserId", sa.BigInteger(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trigger", sa.String(100), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["UserId"], ["Users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Admins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )


def downgrade() -> None:
    op.drop_table("Admins")
    op.drop_table("Configs")
    op.drop_table("Stats")
    op.drop_table("Allowances")
    op.drop_table("Reviews")
    op.drop_table("Limitations")
    op.drop_table("Rates")
    op.drop_table("BankAccounts")
    op.drop_table("Orders")
    op.drop_table("Cards")
    op.drop_table("Banks")
    op.drop_table("Users")
