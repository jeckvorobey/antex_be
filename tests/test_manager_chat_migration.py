from __future__ import annotations

from pathlib import Path


def test_manager_chat_migration_follows_current_head() -> None:
    migration = Path("alembic/versions/032_add_manager_chat_workspace.py").read_text()

    assert 'revision = "032"' in migration
    assert 'down_revision = "031"' in migration
    assert '"ChatConversations"' in migration
    assert '"ChatMessages"' in migration
    assert '"ChatMessageRevisions"' in migration
    assert '"ChatAttachments"' in migration
