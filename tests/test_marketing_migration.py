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
