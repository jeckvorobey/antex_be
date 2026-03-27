"""Загрузка банков из data/banks.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.bank import BankRepository

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "banks.json"


async def seed_banks(db: AsyncSession) -> int:
    if not DATA_FILE.exists():
        logger.warning("banks.json not found at %s", DATA_FILE)
        return 0

    with DATA_FILE.open() as f:
        banks: list[dict] = json.load(f)

    repo = BankRepository(db)
    created = 0
    for bank_data in banks:
        existing = await repo.get_by_code(bank_data["code"])
        if not existing:
            await repo.create(code=bank_data["code"], name=bank_data["name"])
            created += 1

    logger.info("Seeded %d banks", created)
    return created
