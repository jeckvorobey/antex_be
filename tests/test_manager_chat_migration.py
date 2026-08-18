from __future__ import annotations

from io import StringIO

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import JSON, DateTime, LargeBinary, String

from alembic import command
from app.core.config import settings
from app.models.base import Base


def test_manager_chat_revisions_form_one_linear_alembic_head() -> None:
    """Разрыв или fork manager-chat revision graph нарушает deploy contract."""
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["035"]
    revisions = []
    current = script.get_revision("035")
    while current is not None and current.revision != "030":
        revisions.append(current.revision)
        current = script.get_revision(current.down_revision)

    assert revisions == ["035", "034", "033", "032", "031"]


def test_manager_chat_upgrade_and_downgrade_compile_for_postgresql(monkeypatch) -> None:
    """Alembic выполняет offline upgrade и rollback новых revisions без source inspection."""
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+asyncpg://migration:test@localhost/antex_migration_contract",
    )
    upgrade_output = StringIO()
    upgrade_config = Config("alembic.ini", output_buffer=upgrade_output)
    command.upgrade(upgrade_config, "head", sql=True)

    downgrade_output = StringIO()
    downgrade_config = Config("alembic.ini", output_buffer=downgrade_output)
    command.downgrade(downgrade_config, "035:032", sql=True)

    assert upgrade_output.getvalue().strip().endswith("COMMIT;")
    assert downgrade_output.getvalue().strip().endswith("COMMIT;")


def test_attachment_runtime_metadata_matches_durable_delivery_contract() -> None:
    """Runtime metadata содержит payload, media metadata и nullable delivery lease."""
    attachments = Base.metadata.tables["ChatAttachments"]

    assert isinstance(attachments.c.payload.type, LargeBinary)
    assert attachments.c.payload.nullable is True
    assert isinstance(attachments.c.media_metadata.type, JSON)
    assert attachments.c.media_metadata.nullable is True
    assert isinstance(attachments.c.delivery_claim_token.type, String)
    assert attachments.c.delivery_claim_token.type.length == 32
    assert attachments.c.delivery_claim_token.nullable is True
    assert isinstance(attachments.c.delivery_claimed_at.type, DateTime)
    assert attachments.c.delivery_claimed_at.type.timezone is True
    assert attachments.c.delivery_claimed_at.nullable is True
