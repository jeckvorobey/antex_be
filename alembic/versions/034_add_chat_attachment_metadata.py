"""Добавить media metadata вложений manager chat.

Revision ID: 034
Revises: 033
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.databases.migration_compatibility import restore_legacy_main_chat_schema

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Добавить JSON metadata для render/download contract Telegram media."""
    restore_legacy_main_chat_schema(include_payload=True)
    op.add_column("ChatAttachments", sa.Column("media_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Удалить media-specific metadata."""
    op.drop_column("ChatAttachments", "media_metadata")
