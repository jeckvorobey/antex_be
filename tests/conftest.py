from __future__ import annotations

import os
from collections.abc import AsyncIterator

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest-only-32-bytes")

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import *  # noqa: F403
from app.models.base import Base


class FakeRedis:
    """Минимальный изолированный Redis для тестов без внешнего сервиса."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        del key, seconds
        return True


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    """Исключает обращения тестов к локальному либо внешнему Redis."""
    from app.core import redis as redis_module

    redis = FakeRedis()
    monkeypatch.setattr(redis_module, "redis_client", redis)
    return redis


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
