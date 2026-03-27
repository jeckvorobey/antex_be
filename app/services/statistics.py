"""Сервис статистики."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.order import OrderRepository
from app.repositories.stat import StatRepository
from app.repositories.user import UserRepository


async def get_stats(db: AsyncSession, date_from: datetime, date_to: datetime) -> dict:
    user_repo = UserRepository(db)
    order_repo = OrderRepository(db)

    users = await user_repo.get_users_interval(date_from, date_to)
    orders = await order_repo.get_by_interval(date_from, date_to)

    completed = [o for o in orders if o.status == 4]
    cancelled = [o for o in orders if o.status == 5]

    total_rub = sum(o.amountSell for o in completed if o.currencySell == "RUB")
    total_thb = sum(o.amountBuy for o in completed if o.currencyBuy == "THB")

    return {
        "new_users": len(users),
        "total_orders": len(orders),
        "completed_orders": len(completed),
        "cancelled_orders": len(cancelled),
        "total_rub": total_rub,
        "total_thb": total_thb,
    }


async def get_rate_clicks(db: AsyncSession, date_from: datetime, date_to: datetime) -> list:
    repo = StatRepository(db)
    stats = await repo.get_stats_period(date_from, date_to)
    return stats
