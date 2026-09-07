"""Совместимость пересекающихся revision IDs main и dev перед их объединением."""

from __future__ import annotations

import sqlalchemy as sa
from alembic.script import ScriptDirectory

from alembic import context, op

CHAT_TABLES = {"ChatConversations", "ChatMessages", "ChatMessageRevisions", "ChatAttachments"}


def restore_legacy_main_chat_schema(*, include_payload: bool) -> None:
    """Восстанавливает chat-шаги legacy 032/033 внутри текущей транзакции.

    Чистый offline bootstrap уже содержит эти шаги. Online восстановление разрешено
    только для известной main-схемы без таблиц чатов; частичная схема требует разбора.
    Revision не переписывается, существующие данные не удаляются.
    """
    if context.is_offline_mode():
        return

    inspector = sa.inspect(op.get_bind())
    existing = CHAT_TABLES.intersection(inspector.get_table_names())
    if existing == CHAT_TABLES:
        return
    if existing:
        raise RuntimeError("Partial chat schema: legacy migration recovery refused")
    columns = {column["name"] for column in inspector.get_columns("Broadcasts")}
    if "button_type" not in columns:
        raise RuntimeError("Unknown schema: legacy migration recovery refused")

    script = ScriptDirectory.from_config(context.config)
    workspace = script.get_revision("032")
    assert workspace is not None
    workspace.module.upgrade()
    if include_payload:
        payload = script.get_revision("033")
        assert payload is not None
        payload.module.upgrade()
