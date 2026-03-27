"""Репозиторий карт."""

from __future__ import annotations

from sqlalchemy import select

from app.models.card import Card
from app.repositories.base import BaseRepository

CRYPTO_BANKS = ("BNB", "TRON", "USDT")


class CardRepository(BaseRepository[Card]):
    model = Card

    async def bulk_create(self, cards: list[dict]) -> list[Card]:
        objs = [Card(**data) for data in cards]
        self.session.add_all(objs)
        await self.session.flush()
        return objs

    async def get_banks_only(self) -> list[Card]:
        result = await self.session.execute(
            select(Card).where(Card.bank.notin_(CRYPTO_BANKS), Card.isActive.is_(True))
        )
        return list(result.scalars().all())

    async def get_crypto_wallets(self) -> list[Card]:
        result = await self.session.execute(
            select(Card).where(Card.bank.in_(CRYPTO_BANKS), Card.isActive.is_(True))
        )
        return list(result.scalars().all())

    async def toggle_active(self, card_id: int) -> Card | None:
        card = await self.session.get(Card, card_id)
        if card:
            card.isActive = not card.isActive
            await self.session.flush()
        return card
