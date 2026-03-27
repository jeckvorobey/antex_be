"""Загрузка карт из data/cards.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.card import CardRepository

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "cards.json"


async def seed_cards(db: AsyncSession) -> int:
    if not DATA_FILE.exists():
        logger.warning("cards.json not found at %s", DATA_FILE)
        return 0

    with DATA_FILE.open() as f:
        cards: list[dict] = json.load(f)

    repo = CardRepository(db)
    existing = await repo.get_all()
    if existing:
        logger.info("Cards already seeded, skipping")
        return 0

    created_count = 0
    batch = []
    for card_data in cards:
        batch.append({
            "bank": card_data.get("bank", ""),
            "name": card_data.get("name", ""),
            "number": card_data.get("number", ""),
            "isActive": card_data.get("isActive", True),
        })
        created_count += 1

    if batch:
        await repo.bulk_create(batch)

    logger.info("Seeded %d cards", created_count)
    return created_count
