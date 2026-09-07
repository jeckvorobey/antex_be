from __future__ import annotations

import asyncio
import os
import sys
import warnings
from collections.abc import AsyncIterator
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_deployed_revision_035_is_available() -> None:
    """Production DB revision must remain resolvable by every deployed image."""
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_revision("035") is not None
    assert script.get_revision("035").down_revision == "034"


def test_migration_history_has_one_unambiguous_linear_head() -> None:
    """Релиз не должен переиспользовать ID миграций или иметь боковые ветки."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        script = ScriptDirectory.from_config(Config("alembic.ini"))
        revisions = list(script.walk_revisions())
    assert script.get_heads() == ["041"]
    assert len(revisions) == 41
    for current, previous in pairwise(revisions):
        assert current.down_revision == previous.revision
    assert revisions[-1].down_revision is None


@pytest.fixture
async def migration_database() -> AsyncIterator[str]:
    """Создаёт только случайную тестовую БД на явно выбранном loopback PostgreSQL."""
    url = os.environ.get("ANTEX_MIGRATION_TEST_URL")
    if not url:
        pytest.skip("ANTEX_MIGRATION_TEST_URL не задан: PostgreSQL integration opt-in")
    parsed = urlsplit(url)
    assert parsed.hostname in {"127.0.0.1", "localhost"}
    assert parsed.path == "/antex_migration_test"
    assert parsed.port is not None
    control = await asyncpg.connect(url)
    name = f"antex_migration_test_{uuid4().hex}"
    try:
        assert await control.fetchval("SELECT current_database()") == "antex_migration_test"
        await control.execute(f'CREATE DATABASE "{name}"')
        yield urlunsplit(parsed._replace(path=f"/{name}"))
    finally:
        await control.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await control.close()


async def run_upgrade(url: str, revision: str = "head") -> tuple[int, str]:
    """Запускает настоящий Alembic без запуска приложения и внешних сервисов."""
    env = os.environ.copy()
    env["DATABASE_URL"] = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    env["JWT_SECRET"] = "migration-tests-only-secret-at-least-32-bytes"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        revision,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    assert process.returncode is not None
    return process.returncode, stderr.decode()


async def seed_legacy_main(url: str, revision: str) -> None:
    """Воспроизводит опубликованные main 032/033 поверх общей схемы 031."""
    code, error = await run_upgrade(url, "031")
    assert code == 0, error
    connection = await asyncpg.connect(url)
    try:
        await connection.execute("""
            ALTER TABLE "Broadcasts" ADD COLUMN button_type VARCHAR(16) NOT NULL DEFAULT 'url';
            INSERT INTO "Admins" (id, username, password_hash)
            VALUES (1, 'migration-fixture', 'not-a-real-password-hash');
            INSERT INTO "Broadcasts"
                (status, audience_type, text, format, speed_mode_requested,
                 speed_mode_effective, target_rps, worker_count, created_by_admin_id, button_type)
            VALUES ('completed', 'all', 'fixture', 'HTML', 'safe', 'safe', 1, 1, 1, 'web_app');
        """)
        if revision == "033":
            await connection.execute("""
                ALTER TABLE "Admins" ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0;
                ALTER TABLE "Admins" ALTER COLUMN session_version DROP DEFAULT;
                UPDATE "Admins" SET session_version = 7 WHERE id = 1;
            """)
        await connection.execute("UPDATE alembic_version SET version_num = $1", revision)
    finally:
        await connection.close()


@pytest.mark.parametrize("start", ["clean", "dev033", "dev035", "dev041", "main032", "main033"])
async def test_upgrade_supported_postgresql_histories(migration_database: str, start: str) -> None:
    """Каждая поддержанная история достигает head без утраты существующих значений."""
    if start.startswith("main"):
        await seed_legacy_main(migration_database, start.removeprefix("main"))
    elif start.startswith("dev"):
        code, error = await run_upgrade(migration_database, start.removeprefix("dev"))
        assert code == 0, error
    code, error = await run_upgrade(migration_database)
    assert code == 0, error
    connection = await asyncpg.connect(migration_database)
    try:
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == "041"
        for table, column in [
            ("ChatConversations", "manager_id"),
            ("ChatMessages", "forward_source_message_id"),
            ("ChatAttachments", "payload"),
            ("ChatAttachments", "media_metadata"),
            ("Broadcasts", "button_type"),
            ("Admins", "session_version"),
            ("OrderTelegramSyncTasks", "OrderId"),
        ]:
            assert await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = $1 AND column_name = $2)",
                table,
                column,
            ), (table, column)
        if start.startswith("main"):
            assert await connection.fetchval('SELECT button_type FROM "Broadcasts"') == "web_app"
            expected = 7 if start == "main033" else 0
            assert await connection.fetchval('SELECT session_version FROM "Admins"') == expected
    finally:
        await connection.close()
    code, error = await run_upgrade(migration_database)
    assert code == 0, error


async def test_partial_legacy_chat_schema_is_not_silently_repaired(migration_database: str) -> None:
    """Неизвестная частичная схема останавливает upgrade без изменения revision."""
    await seed_legacy_main(migration_database, "033")
    connection = await asyncpg.connect(migration_database)
    try:
        await connection.execute('CREATE TABLE "ChatConversations" (id INTEGER PRIMARY KEY)')
        code, _ = await run_upgrade(migration_database)
        assert code != 0
        assert await connection.fetchval("SELECT version_num FROM alembic_version") == "033"
        assert await connection.fetchval('SELECT session_version FROM "Admins"') == 7
        assert await connection.fetchval("SELECT to_regclass('\"ChatAttachments\"')") is None
    finally:
        await connection.close()
