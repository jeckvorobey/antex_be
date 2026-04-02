"""Скрипт базового сидирования."""

from __future__ import annotations

import asyncio

from app.core.database import async_session
from app.databases.seeds.seed_admin import seed_admin


async def main() -> None:
    async with async_session() as session, session.begin():
        await seed_admin(session)


if __name__ == "__main__":
    asyncio.run(main())
