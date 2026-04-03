"""TDD тесты для AllowanceRepository."""
from __future__ import annotations

import pytest

from app.repositories.allowance import AllowanceRepository
from app.repositories.config import ConfigRepository


async def test_get_value_returns_default_on_fresh_db(db_session) -> None:
    repo = AllowanceRepository(db_session)
    value = await repo.get_value()
    # Дефолт в модели Config.allowance = 2.0
    assert value == pytest.approx(2.0)


async def test_get_value_reflects_updated_allowance(db_session) -> None:
    config_repo = ConfigRepository(db_session)
    await config_repo.set_allowance(3.5)
    await db_session.flush()

    allowance_repo = AllowanceRepository(db_session)
    value = await allowance_repo.get_value()
    assert value == pytest.approx(3.5)


async def test_get_value_handles_zero_allowance(db_session) -> None:
    config_repo = ConfigRepository(db_session)
    await config_repo.set_allowance(0.0)
    await db_session.flush()

    allowance_repo = AllowanceRepository(db_session)
    value = await allowance_repo.get_value()
    assert value == pytest.approx(0.0)
