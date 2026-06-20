from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "alembic/versions/003_add_broadcasts.py"


def load_migration_module():
    spec = importlib.util.spec_from_file_location("broadcasts_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_active_broadcast_singleton_index_expression_is_postgresql_safe() -> None:
    broadcasts_migration = load_migration_module()
    metadata = sa.MetaData()
    table = sa.Table(
        "Broadcasts",
        metadata,
        sa.Column("id", sa.Integer()),
        sa.Index(
            "uq_broadcast_active_singleton",
            broadcasts_migration.ACTIVE_BROADCAST_INDEX_EXPRESSION,
            unique=True,
            postgresql_where=sa.text("status IN ('pending', 'running')"),
        ),
    )

    index = next(iter(table.indexes))
    compiled = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert 'ON "Broadcasts" ((1))' in compiled
