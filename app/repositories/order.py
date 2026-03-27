"""Репозиторий заявок."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.models.order import Order
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    model = Order

    async def get_one(self, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .where(Order.id == order_id, Order.destroyTime.is_(None))
            .options(
                selectinload(Order.user),
                selectinload(Order.bank),
                selectinload(Order.card),
                selectinload(Order.bank_account),
                selectinload(Order.review),
            )
        )
        return result.scalar_one_or_none()

    async def update_status(self, order_id: int, status: int) -> Order | None:
        order = await self.session.get(Order, order_id)
        if order:
            order.status = status
            await self.session.flush()
        return order

    async def cancel(self, order_id: int) -> Order | None:
        from app.enums.order import OrderStatus
        return await self.update_status(order_id, OrderStatus.CANCELLED)

    async def soft_delete(self, order_id: int) -> Order | None:
        order = await self.session.get(Order, order_id)
        if order:
            order.destroyTime = datetime.utcnow()
            await self.session.flush()
        return order

    async def get_by_interval(self, date_from: datetime, date_to: datetime) -> list[Order]:
        result = await self.session.execute(
            select(Order).where(
                Order.createdAt >= date_from,
                Order.createdAt <= date_to,
                Order.destroyTime.is_(None),
            )
        )
        return list(result.scalars().all())

    async def check_open(self, user_id: int) -> Order | None:
        from app.enums.order import OrderStatus
        result = await self.session.execute(
            select(Order).where(
                Order.UserId == user_id,
                Order.status.in_([OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.PROCESSING]),
                Order.destroyTime.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_user_orders(self, user_id: int, limit: int = 10) -> list[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.UserId == user_id, Order.destroyTime.is_(None))
            .order_by(desc(Order.createdAt))
            .limit(limit)
        )
        return list(result.scalars().all())
