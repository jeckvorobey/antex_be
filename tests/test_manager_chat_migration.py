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

    assert script.get_heads() == ["036"]
    revisions = []
    current = script.get_revision("036")
    while current is not None and current.revision != "030":
        revisions.append(current.revision)
        current = script.get_revision(current.down_revision)

    assert revisions == ["036", "035", "034", "033", "032", "031"]


def test_manager_chat_upgrade_and_downgrade_emit_attachment_contract(monkeypatch) -> None:
    """Alembic PostgreSQL DDL реализует upgrade/rollback attachment revisions."""
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
    command.downgrade(downgrade_config, "036:032", sql=True)

    upgrade_sql = " ".join(upgrade_output.getvalue().split())
    downgrade_sql = " ".join(downgrade_output.getvalue().split())

    expected_upgrade_statements = (
        'ALTER TABLE "ChatAttachments" ALTER COLUMN telegram_file_id DROP NOT NULL;',
        'ALTER TABLE "ChatAttachments" ADD COLUMN payload BYTEA;',
        'ALTER TABLE "ChatAttachments" ADD COLUMN media_metadata JSON;',
        'ALTER TABLE "ChatAttachments" ADD COLUMN delivery_claim_token VARCHAR(32);',
        'ALTER TABLE "ChatAttachments" ADD COLUMN delivery_claimed_at TIMESTAMP WITH TIME ZONE;',
        'ALTER TABLE "ChatMessages" ADD COLUMN delivery_claim_token VARCHAR(32);',
        'ALTER TABLE "ChatMessages" ADD COLUMN delivery_claimed_at TIMESTAMP WITH TIME ZONE;',
    )
    expected_downgrade_statements = (
        'ALTER TABLE "ChatAttachments" DROP COLUMN delivery_claimed_at;',
        'ALTER TABLE "ChatAttachments" DROP COLUMN delivery_claim_token;',
        'ALTER TABLE "ChatMessages" DROP COLUMN delivery_claimed_at;',
        'ALTER TABLE "ChatMessages" DROP COLUMN delivery_claim_token;',
        'ALTER TABLE "ChatAttachments" DROP COLUMN media_metadata;',
        'DELETE FROM "ChatAttachments" WHERE telegram_file_id IS NULL;',
        'ALTER TABLE "ChatAttachments" ALTER COLUMN telegram_file_id SET NOT NULL;',
        'ALTER TABLE "ChatAttachments" DROP COLUMN payload;',
    )

    for statement in expected_upgrade_statements:
        assert upgrade_sql.count(statement) == 1
    for statement in expected_downgrade_statements:
        assert downgrade_sql.count(statement) == 1


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

    messages = Base.metadata.tables["ChatMessages"]
    assert isinstance(messages.c.delivery_claim_token.type, String)
    assert messages.c.delivery_claim_token.type.length == 32
    assert messages.c.delivery_claim_token.nullable is True
    assert isinstance(messages.c.delivery_claimed_at.type, DateTime)
    assert messages.c.delivery_claimed_at.type.timezone is True
    assert messages.c.delivery_claimed_at.nullable is True
