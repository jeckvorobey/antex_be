"""Add Telegram profile photo URL to users."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("Users", sa.Column("photo_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("Users", "photo_url")
