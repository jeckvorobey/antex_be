"""Remove Users.referred_by — SSOT is UserAcquisitions.referrer_user_id.

Revision ID: 026
Revises: 025
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Backfill: move referred_by -> UserAcquisitions.referrer_user_id
    #    for users with existing acquisition (legacy/direct)
    #    but empty referrer_user_id.
    op.execute(
        """
        UPDATE "UserAcquisitions" ua
        SET referrer_user_id = u.referred_by,
            source_type = 'referral'
        FROM "Users" u
        WHERE ua.user_id = u.id
          AND u.referred_by IS NOT NULL
          AND ua.referrer_user_id IS NULL
        """
    )

    # 2. For users without any acquisition (should not happen,
    #    but just in case) — create acquisition.
    op.execute(
        """
        INSERT INTO "UserAcquisitions" (user_id, source_type, referrer_user_id, acquired_at)
        SELECT u.id, 'referral', u.referred_by, u."createdAt"
        FROM "Users" u
        WHERE u.referred_by IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM "UserAcquisitions" ua WHERE ua.user_id = u.id
          )
        """
    )

    # 3. Удалить дублирующую колонку.
    op.drop_column("Users", "referred_by")


def downgrade() -> None:
    op.add_column(
        "Users",
        sa.Column("referred_by", sa.Integer(), sa.ForeignKey("Users.id"), nullable=True),
    )
    op.execute(
        """
        UPDATE "Users" u
        SET referred_by = ua.referrer_user_id
        FROM "UserAcquisitions" ua
        WHERE ua.user_id = u.id
          AND ua.source_type = 'referral'
          AND ua.referrer_user_id IS NOT NULL
        """
    )
