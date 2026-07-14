"""Remove obsolete campaign medium and add soft deletion for marketing platforms."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Удаляет medium и добавляет timestamp мягкого удаления платформы."""
    op.drop_column("MarketingCampaigns", "medium")
    op.add_column(
        "MarketingPlatforms",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Возвращает прежнюю структуру при откате миграции."""
    op.drop_column("MarketingPlatforms", "deleted_at")
    op.add_column("MarketingCampaigns", sa.Column("medium", sa.String(length=128), nullable=True))
