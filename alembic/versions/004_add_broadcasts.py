"""Add broadcasts table.

Revision ID: 004
Revises: 003
Create Date: 2026-03-30 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "Broadcasts",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            comment="Уникальный идентификатор рассылки",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            comment="Текущий статус рассылки: pending, running, completed или failed",
        ),
        sa.Column(
            "audience_type",
            sa.String(length=64),
            nullable=False,
            comment="Тип аудитории, по которой собирались получатели рассылки",
        ),
        sa.Column(
            "text",
            sa.Text(),
            nullable=False,
            comment="Исходный текст сообщения, который был задан администратором",
        ),
        sa.Column(
            "format",
            sa.String(length=16),
            nullable=False,
            comment="Формат текста сообщения: plain или html",
        ),
        sa.Column(
            "button_text",
            sa.String(length=255),
            nullable=True,
            comment="Подпись кнопки под сообщением, если кнопка была задана",
        ),
        sa.Column(
            "button_url",
            sa.Text(),
            nullable=True,
            comment="Ссылка URL или WebApp, которая открывается по кнопке",
        ),
        sa.Column(
            "speed_mode_requested",
            sa.String(length=16),
            nullable=False,
            comment="Запрошенный режим скорости рассылки: free или paid",
        ),
        sa.Column(
            "speed_mode_effective",
            sa.String(length=16),
            nullable=False,
            comment="Фактически использованный режим скорости рассылки",
        ),
        sa.Column(
            "target_rps",
            sa.Integer(),
            nullable=False,
            comment="Целевой лимит сообщений в секунду для данной рассылки",
        ),
        sa.Column(
            "worker_count",
            sa.Integer(),
            nullable=False,
            comment="Количество параллельных async worker'ов, отправляющих сообщения",
        ),
        sa.Column(
            "total_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Общее количество получателей, попавших в рассылку",
        ),
        sa.Column(
            "success_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Количество успешно доставленных сообщений",
        ),
        sa.Column(
            "failed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Количество сообщений, которые не удалось доставить",
        ),
        sa.Column(
            "created_by_admin_id",
            sa.Integer(),
            sa.ForeignKey("Admins.id"),
            nullable=False,
            comment="Идентификатор администратора, который создал рассылку",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Время фактического начала отправки рассылки",
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Время окончания обработки рассылки",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Последняя критическая ошибка, из-за которой рассылка завершилась сбоем",
        ),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Время создания записи о рассылке",  # noqa: RUF001
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Время последнего обновления записи о рассылке",  # noqa: RUF001
        ),
    )
    op.create_index(
        "uq_broadcast_active_singleton",
        "Broadcasts",
        [sa.literal_column("1")],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_broadcast_active_singleton", table_name="Broadcasts")
    op.drop_table("Broadcasts")
