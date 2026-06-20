"""Add optional unique email for admins.

Revision ID: 012
Revises: 011
Create Date: 2026-06-18 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("Admins", sa.Column("email", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_admins_email", "Admins", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_admins_email", "Admins", type_="unique")
    op.drop_column("Admins", "email")
