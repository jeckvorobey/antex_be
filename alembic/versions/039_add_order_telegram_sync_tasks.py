"""Добавляет единый workflow и задания Telegram-синхронизации.

Revision ID: 039
Revises: 038
Create Date: 2026-09-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("Orders", sa.Column("ManagerId", sa.Integer(), nullable=True))
    op.add_column(
        "Orders",
        sa.Column("managerNotificationChatId", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "Orders",
        sa.Column("managerNotificationMessageId", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_manager_id_users",
        "Orders",
        "Users",
        ["ManagerId"],
        ["id"],
    )
    op.create_table(
        "OrderTelegramSyncTasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("OrderId", sa.Integer(), nullable=False),
        sa.Column("target", sa.String(length=16), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attemptCount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nextAttemptAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lockedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deliveredAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lastErrorCode", sa.String(length=64), nullable=True),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["OrderId"], ["Orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "OrderId",
            "status",
            "target",
            name="uq_order_telegram_sync_task",
        ),
    )
    op.create_index(
        "ix_order_telegram_sync_tasks_due",
        "OrderTelegramSyncTasks",
        ["state", "nextAttemptAt"],
    )


def downgrade() -> None:
    op.drop_index("ix_order_telegram_sync_tasks_due", table_name="OrderTelegramSyncTasks")
    op.drop_table("OrderTelegramSyncTasks")
    op.drop_constraint("fk_orders_manager_id_users", "Orders", type_="foreignkey")
    op.drop_column("Orders", "managerNotificationMessageId")
    op.drop_column("Orders", "managerNotificationChatId")
    op.drop_column("Orders", "ManagerId")
