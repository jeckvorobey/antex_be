"""Репозиторий отзывов."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.review import Review
from app.repositories.base import BaseRepository


class ReviewRepository(BaseRepository[Review]):
    model = Review

    async def get_one_with_order(self, review_id: int) -> Review | None:
        result = await self.session.execute(
            select(Review)
            .where(Review.id == review_id)
            .options(selectinload(Review.order))
        )
        return result.scalar_one_or_none()

    async def get_by_order(self, order_id: int) -> Review | None:
        result = await self.session.execute(
            select(Review).where(Review.OrderId == order_id)
        )
        return result.scalar_one_or_none()
