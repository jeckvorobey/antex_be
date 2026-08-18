from __future__ import annotations

from pathlib import Path


def test_manager_chat_migration_follows_order_delivery_revision() -> None:
    migration = Path("alembic/versions/032_add_manager_chat_workspace.py").read_text()

    assert 'revision = "032"' in migration
    assert 'down_revision = "031"' in migration
    assert '"ChatConversations"' in migration
    assert '"ChatMessages"' in migration
    assert '"ChatMessageRevisions"' in migration
    assert '"ChatAttachments"' in migration


def test_attachment_payload_migration_follows_manager_chat_revision() -> None:
    migration = Path("alembic/versions/033_add_chat_attachment_payload.py").read_text()

    assert 'revision = "033"' in migration
    assert 'down_revision = "032"' in migration
    assert '"payload"' in migration
    assert '"telegram_file_id"' in migration
