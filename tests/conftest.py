from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import *  # noqa: F403
from app.models.base import Base


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def tg_user_payload() -> dict[str, object]:
    return {
        "id": 123456,
        "username": "initial_user",
        "first_name": "Initial",
        "last_name": "User",
        "language_code": "en",
        "is_bot": False,
        "is_premium": True,
    }
