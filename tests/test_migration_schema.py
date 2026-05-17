from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from app.models.base import Base

BACK_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_ENV_PATH = BACK_ROOT / "alembic/env.py"
EXPECTED_TABLES = {
    "Admins",
    "Cities",
    "Configs",
    "Rates",
    "Users",
    "Orders",
    "Broadcasts",
}
EXPECTED_BROADCAST_COLUMNS = {
    "id",
    "status",
    "audience_type",
    "text",
    "format",
    "speed_mode_requested",
    "speed_mode_effective",
    "target_rps",
    "worker_count",
    "created_by_admin_id",
    "createdAt",
    "updatedAt",
}


def load_alembic_env_module():
    """Загружает env.py как обычный модуль для проверки Alembic metadata."""
    spec = importlib.util.spec_from_file_location("alembic_env_for_test", ALEMBIC_ENV_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_upgrade_sql_creates_country_enum_once() -> None:
    """Фиксирует, что чистый PostgreSQL bootstrap не создает country_enum дважды."""
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://antex:antex@localhost:5432/antex"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACK_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("CREATE TYPE country_enum") == 1


def test_alembic_load_models_includes_all_tables() -> None:
    """Проверяет, что env.py подхватывает общий экспорт моделей backend."""
    alembic_env = load_alembic_env_module()

    alembic_env.load_models()

    assert set(Base.metadata.tables) >= EXPECTED_TABLES


def test_model_metadata_contains_required_migration_columns() -> None:
    """Проверяет обязательные колонки новой margin-модели и broadcasts."""
    load_alembic_env_module().load_models()

    assert "margin" in Base.metadata.tables["Rates"].columns
    assert "country" in Base.metadata.tables["Rates"].columns
    assert "allowance" not in Base.metadata.tables["Configs"].columns
    assert set(Base.metadata.tables["Broadcasts"].columns.keys()) >= EXPECTED_BROADCAST_COLUMNS
