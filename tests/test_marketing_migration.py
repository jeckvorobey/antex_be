from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACK_ROOT = Path(__file__).resolve().parents[1]


def test_marketing_migration_offline_sql_contains_tables_constraints_and_indexes() -> None:
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
    for table in ("MarketingCampaigns", "MarketingAttributions", "MarketingDailyMetrics"):
        assert f'CREATE TABLE "{table}"' in result.stdout
    assert "uq_marketing_daily_campaign_date" in result.stdout
    assert "ix_marketing_attributions_campaign_attributed" in result.stdout


def test_attribution_migration_offline_sql_contains_snapshot_constraints_and_indexes() -> None:
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
    for table in (
        "UserAcquisitions",
        "MarketingTouches",
        "OrderAttributions",
        "AttributionAuditEvents",
    ):
        assert f'CREATE TABLE "{table}"' in result.stdout
    for constraint in (
        "ck_user_acquisition_source",
        "ck_order_attribution_touch",
        "ck_order_attribution_lookback",
        "ck_config_marketing_attribution_window",
        "ix_marketing_touches_user_touched",
        "ix_order_attributions_campaign_attributed",
    ):
        assert constraint in result.stdout
    assert 'INSERT INTO "UserAcquisitions"' in result.stdout
    assert '"createdAt"' in result.stdout
    assert "'legacy'" in result.stdout
    assert 'INSERT INTO "OrderAttributions"' in result.stdout
    assert "legacy_trusted_telegram_auth" in result.stdout
    assert "'reengagement'" in result.stdout
    assert "interval '7 days'" in result.stdout


def test_attribution_migration_does_not_invent_acquisition_from_legacy_marketing_rows() -> None:
    migration = (
        BACK_ROOT / "alembic/versions/024_add_referral_marketing_attribution.py"
    ).read_text()

    acquisition_backfill = migration.split('INSERT INTO "MarketingTouches"', maxsplit=1)[0]
    assert 'FROM "MarketingAttributions"' not in acquisition_backfill
    assert "never derive a campaign acquisition" in migration


def test_referral_ssot_migration_backfills_acquisition_and_drops_users_duplicate() -> None:
    migration = (BACK_ROOT / "alembic/versions/026_remove_users_referred_by.py").read_text()

    assert 'UPDATE "UserAcquisitions"' in migration
    assert 'FROM "Users"' in migration
    assert 'drop_column("Users", "referred_by")' in migration
    assert migration.index('UPDATE "UserAcquisitions"') < migration.index(
        'drop_column("Users", "referred_by")'
    )
