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
    "OrderNumberCounters",
    "OrderTelegramSyncTasks",
    "Broadcasts",
    "SiteLeads",
    "MarketingPlatforms",
    "MarketingCurrencies",
}
EXPECTED_BROADCAST_COLUMNS = {
    "id",
    "status",
    "audience_type",
    "text",
    "format",
    "button_type",
    "speed_mode_requested",
    "speed_mode_effective",
    "target_rps",
    "worker_count",
    "created_by_admin_id",
    "createdAt",
    "updatedAt",
}
EXPECTED_ORDER_COLUMNS = {
    "id",
    "UserId",
    "ManagerId",
    "CityId",
    "country",
    "currencySell",
    "amountSell",
    "currencyBuy",
    "amountBuy",
    "rate",
    "deliveryRate",
    "status",
    "contactTelegram",
    "methodGet",
    "publicNumber",
    "userNotificationMessageId",
    "managerNotificationChatId",
    "managerNotificationMessageId",
    "endTime",
    "destroyTime",
    "createdAt",
    "updatedAt",
}
EXPECTED_ORDER_TELEGRAM_SYNC_TASK_COLUMNS = {
    "id",
    "OrderId",
    "target",
    "status",
    "state",
    "attemptCount",
    "nextAttemptAt",
    "lockedAt",
    "deliveredAt",
    "lastErrorCode",
    "createdAt",
    "updatedAt",
}
EXPECTED_SITE_LEAD_COLUMNS = {
    "id",
    "messenger",
    "contact",
    "topic",
    "message",
    "source",
    "createdAt",
    "updatedAt",
}
EXPECTED_REFERRAL_CONFIG_COLUMNS = {
    "referral_percent",
    "referral_min_withdraw",
    "referral_max_withdraw",
    "aex_rate",
    "aex_withdraw_limit",
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


def test_internal_rates_migration_hides_existing_reserved_pairs() -> None:
    """Migration 023 должна скрывать зарезервированные пары из legacy-базы."""
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
    assert "PARTITION BY upper(currency)" in result.stdout
    assert "ranked_rates.row_number > 1" in result.stdout
    assert (
        "SET currency = upper(currency)\n            WHERE currency <> upper(currency)"
        in result.stdout
    )
    assert 'UPDATE "Rates"' in result.stdout
    assert "SET is_internal = true, country = NULL" in result.stdout
    assert "currency IN ('USDTRUB', 'RUBUSDT')" in result.stdout


def test_internal_exchange_country_migration_extends_shared_enum() -> None:
    """Migration 025 должна добавить псевдострану внутренних заявок."""
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
    assert "ALTER TYPE country_enum ADD VALUE IF NOT EXISTS 'internal'" in result.stdout


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
    assert set(Base.metadata.tables["Configs"].columns.keys()) >= EXPECTED_REFERRAL_CONFIG_COLUMNS
    assert set(Base.metadata.tables["Broadcasts"].columns.keys()) >= EXPECTED_BROADCAST_COLUMNS
    assert set(Base.metadata.tables["Orders"].columns.keys()) >= EXPECTED_ORDER_COLUMNS
    sync_tasks = Base.metadata.tables["OrderTelegramSyncTasks"]
    assert set(sync_tasks.columns.keys()) >= EXPECTED_ORDER_TELEGRAM_SYNC_TASK_COLUMNS
    assert {column.name for column in sync_tasks.primary_key.columns} == {"id"}
    assert any(
        {column.name for column in constraint.columns} == {"OrderId", "status", "target"}
        for constraint in sync_tasks.constraints
        if hasattr(constraint, "columns") and constraint.__class__.__name__ == "UniqueConstraint"
    )
    assert any(
        index.name == "ix_order_telegram_sync_tasks_due"
        and [column.name for column in index.columns] == ["state", "nextAttemptAt"]
        for index in sync_tasks.indexes
    )
    assert set(Base.metadata.tables["SiteLeads"].columns.keys()) >= EXPECTED_SITE_LEAD_COLUMNS
    assert {"id", "slug", "name"} <= set(Base.metadata.tables["MarketingPlatforms"].columns.keys())
    assert {"id", "code", "name"} <= set(Base.metadata.tables["MarketingCurrencies"].columns.keys())
    assert "address" not in Base.metadata.tables["Orders"].columns
    assert "cashDeliveryFee" not in Base.metadata.tables["Orders"].columns
    assert Base.metadata.tables["Orders"].columns["deliveryRate"].nullable is True
    assert Base.metadata.tables["Orders"].columns["CityId"].nullable is True
    assert Base.metadata.tables["Orders"].columns["country"].nullable is False
    write_access = Base.metadata.tables["Users"].columns["telegram_write_access"]
    assert write_access.nullable is False
    assert write_access.server_default is not None


def test_broadcast_button_type_migration_is_safe_for_existing_rows() -> None:
    """Новая колонка должна помечать старые рассылки как обычные URL-кнопки."""
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
    assert (
        "ALTER TABLE \"Broadcasts\" ADD COLUMN button_type VARCHAR(16) DEFAULT 'url' NOT NULL"
    ) in result.stdout


def test_write_access_migration_adds_non_nullable_false_default() -> None:
    """Ловит миграцию, небезопасную для уже существующих Users."""
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
    assert "ADD COLUMN telegram_write_access BOOLEAN DEFAULT false NOT NULL" in result.stdout
