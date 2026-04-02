"""Initial clean schema.

Revision ID: 001
Revises:
Create Date: 2026-04-02 00:00:00
"""
# ruff: noqa: E501, I001

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

country_enum = sa.Enum("thailand", "vietnam", name="country_enum")


def upgrade() -> None:
    country_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "Admins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "Cities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", country_enum, nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "Rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=20), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("currency"),
    )

    op.create_table(
        "Users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=10), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("session", sa.Text(), nullable=True),
        sa.Column("chatId", sa.BigInteger(), nullable=True),
        sa.Column("role", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["city_id"], ["Cities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )

    op.create_index(
        "ix_users_unique_manager_per_city",
        "Users",
        ["city_id"],
        unique=True,
        postgresql_where=sa.text("role = 2 AND city_id IS NOT NULL"),
        sqlite_where=sa.text("role = 2 AND city_id IS NOT NULL"),
    )

    op.create_table(
        "Orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("UserId", sa.Integer(), nullable=False),
        sa.Column("CityId", sa.Integer(), nullable=False),
        sa.Column("currencySell", sa.String(length=20), nullable=False),
        sa.Column("amountSell", sa.Integer(), nullable=False),
        sa.Column("currencyBuy", sa.String(length=20), nullable=False),
        sa.Column("amountBuy", sa.Float(), nullable=True),
        sa.Column("rate", sa.Float(), nullable=True),
        sa.Column("status", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("contactTelegram", sa.String(length=255), nullable=True),
        sa.Column("methodGet", sa.String(length=20), nullable=True),
        sa.Column("endTime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("destroyTime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("createdAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["CityId"], ["Cities.id"]),
        sa.ForeignKeyConstraint(["UserId"], ["Users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(sa.text("INSERT INTO \"Configs\" (id, enabled) VALUES (1, true)"))


def downgrade() -> None:
    op.drop_table("Orders")
    op.drop_index("ix_users_unique_manager_per_city", table_name="Users")
    op.drop_table("Users")
    op.drop_table("Rates")
    op.drop_table("Configs")
    op.drop_table("Cities")
    op.drop_table("Admins")
    country_enum.drop(op.get_bind(), checkfirst=True)
