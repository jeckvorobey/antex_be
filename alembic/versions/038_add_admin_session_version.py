"""Добавляет версию сессии администратора.

Revision ID: 038
Revises: 037
Create Date: 2026-08-31
"""

import sqlalchemy as sa

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавляет версию admin-session, равную нулю для имеющихся строк."""
    op.add_column(
        "Admins",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("Admins", "session_version", server_default=None)


def downgrade() -> None:
    op.drop_column("Admins", "session_version")
