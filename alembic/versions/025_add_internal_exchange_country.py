"""Добавить псевдострану для внутренних ATXG-выплат.

Revision ID: 025
Revises: 024
Create Date: 2026-07-22 17:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Расширяет общий PostgreSQL enum без изменения существующих строк."""
    op.execute(sa.text("ALTER TYPE country_enum ADD VALUE IF NOT EXISTS 'internal'"))


def downgrade() -> None:
    """Оставляет совместимое значение перечисления без небезопасного пересоздания типа."""
