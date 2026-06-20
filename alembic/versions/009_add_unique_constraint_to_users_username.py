"""Add unique constraint to users.username."""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_users_username", "Users", ["username"])


def downgrade() -> None:
    op.drop_constraint("uq_users_username", "Users", type_="unique")
