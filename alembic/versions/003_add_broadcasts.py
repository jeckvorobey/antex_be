"""Add broadcasts table.

Revision ID: 003
Revises: 002
Create Date: 2026-05-08 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None
ACTIVE_BROADCAST_INDEX_EXPRESSION = sa.text("(1)")


def upgrade() -> None:
    op.create_table(
        "Broadcasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("audience_type", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("button_text", sa.String(length=255), nullable=True),
        sa.Column("button_url", sa.Text(), nullable=True),
        sa.Column("speed_mode_requested", sa.String(length=16), nullable=False),
        sa.Column("speed_mode_effective", sa.String(length=16), nullable=False),
        sa.Column("target_rps", sa.Integer(), nullable=False),
        sa.Column("worker_count", sa.Integer(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["Admins.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_broadcast_active_singleton",
        "Broadcasts",
        [ACTIVE_BROADCAST_INDEX_EXPRESSION],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_broadcast_active_singleton", table_name="Broadcasts")
    op.drop_table("Broadcasts")
