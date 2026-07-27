"""Добавить UTC-расписание менеджеров в singleton Configs.

Revision ID: 027
Revises: 026
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет безопасный ежедневный UTC-график, соответствующий бизнес-настройке."""
    op.add_column(
        "Configs",
        sa.Column(
            "manager_schedule_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "Configs",
        sa.Column(
            "manager_working_days_utc",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[1, 2, 3, 4, 5, 6, 7]'"),
        ),
    )
    op.add_column(
        "Configs",
        sa.Column("manager_start_time_utc", sa.Time(), nullable=False, server_default="06:00:00"),
    )
    op.add_column(
        "Configs",
        sa.Column("manager_end_time_utc", sa.Time(), nullable=False, server_default="18:00:00"),
    )
    op.alter_column("Configs", "manager_schedule_enabled", server_default=None)
    op.alter_column("Configs", "manager_working_days_utc", server_default=None)
    op.alter_column("Configs", "manager_start_time_utc", server_default=None)
    op.alter_column("Configs", "manager_end_time_utc", server_default=None)


def downgrade() -> None:
    """Удаляет поля расписания при полном rollback совместимой версии приложения."""
    op.drop_column("Configs", "manager_end_time_utc")
    op.drop_column("Configs", "manager_start_time_utc")
    op.drop_column("Configs", "manager_working_days_utc")
    op.drop_column("Configs", "manager_schedule_enabled")
