"""Добавить эффективный курс доставки в заявки.

Revision ID: 031
Revises: 030
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет nullable-курс без backfill legacy-заявок."""
    op.add_column("Orders", sa.Column("deliveryRate", sa.Float(), nullable=True))


def downgrade() -> None:
    """Удаляет эффективный курс доставки."""
    op.drop_column("Orders", "deliveryRate")
