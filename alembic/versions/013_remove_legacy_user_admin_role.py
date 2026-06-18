"""Normalize legacy user admin role to manager.

Revision ID: 013
Revises: 012
Create Date: 2026-06-18 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None

LEGACY_ADMIN_ROLE = 1
MANAGER_ROLE = 2


def upgrade() -> None:
    op.execute(
        sa.text(
            'UPDATE "Users" SET role = :manager_role WHERE role = :legacy_admin_role'
        ).bindparams(manager_role=MANAGER_ROLE, legacy_admin_role=LEGACY_ADMIN_ROLE)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            'UPDATE "Users" SET role = :legacy_admin_role WHERE role = :manager_role'
        ).bindparams(legacy_admin_role=LEGACY_ADMIN_ROLE, manager_role=MANAGER_ROLE)
    )
