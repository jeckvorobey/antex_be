"""Скрипт базового сидирования."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    # Позволяет запускать сидирование документированной командой из README.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.database import async_session
from app.databases.seeds.seed_admin import seed_admin
from app.databases.seeds.seed_cities import seed_cities


async def main() -> None:
    async with async_session() as session, session.begin():
        await seed_admin(session)
        await seed_cities(session)


if __name__ == "__main__":
    asyncio.run(main())
