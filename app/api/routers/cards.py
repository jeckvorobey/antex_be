"""Роутер карт (публичный — только активные)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.repositories.card import CardRepository
from app.schemas.card import CardOut

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.get("", response_model=list[CardOut])
async def get_cards(db: DbDep) -> list[CardOut]:
    repo = CardRepository(db)
    cards = await repo.get_all()
    return [CardOut.model_validate(c) for c in cards if c.isActive]
