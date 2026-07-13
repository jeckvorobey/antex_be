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
