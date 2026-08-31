from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.databases.seeds.seed_admin import seed_admin
from app.repositories.admin import AdminRepository


@pytest.mark.asyncio
async def test_seed_admin_fails_without_bootstrap_password(db_session: AsyncSession) -> None:
    """Seed не должен создавать admin при известном пароле."""
    with pytest.raises(RuntimeError, match="ADMIN_BOOTSTRAP_PASSWORD"):
        await seed_admin(db_session)

    assert await AdminRepository(db_session).get_by_username("admin") is None
