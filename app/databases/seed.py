"""Оркестратор seed-скриптов."""

from __future__ import annotations

import asyncio
import logging

from app.core.database import get_db_session
from app.databases.seeds.seed_banks import seed_banks
from app.databases.seeds.seed_cards import seed_cards

logger = logging.getLogger(__name__)


async def run_seeds() -> None:
    logger.info("Running seeds...")
    async for db in get_db_session():
        async with db:
            await seed_banks(db)
            await seed_cards(db)
            await db.commit()
    logger.info("Seeds complete.")


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    asyncio.run(run_seeds())
