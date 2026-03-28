"""Сервис заявок на обмен."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.order import MethodGet, OrderStatus
from app.exceptions import AntExException
from app.repositories.limitation import LimitationRepository
from app.repositories.order import OrderRepository
from app.schemas.order import OrderCreate, OrderOut


async def create_order(db: AsyncSession, user_id: int, data: OrderCreate) -> OrderOut:
    order_repo = OrderRepository(db)

    # Проверяем нет ли уже открытой заявки
    existing = await order_repo.check_open(user_id)
    if existing:
        raise AntExException("User already has an open order", code="ORDER_ALREADY_EXISTS", status_code=409)

    order = await order_repo.create(
        UserId=user_id,
        BankId=data.BankId,
        CardId=data.CardId,
        currencySell=data.currencySell,
        amountSell=data.amountSell,
        currencyBuy=data.currencyBuy,
        amountBuy=data.amountBuy,
        rate=data.rate,
        address=data.address,
        contactTelegram=data.contactTelegram,
        methodGet=data.methodGet,
        status=OrderStatus.NEW,
    )
    return OrderOut.model_validate(order)


async def confirm_payment(db: AsyncSession, order_id: int) -> OrderOut:
    repo = OrderRepository(db)
    order = await repo.update_status(order_id, OrderStatus.CONFIRMED)
    if not order:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)
    await db.refresh(order)
    return OrderOut.model_validate(order)


async def cancel_order(db: AsyncSession, order_id: int) -> OrderOut:
    order_repo = OrderRepository(db)
    lim_repo = LimitationRepository(db)

    order = await order_repo.get_one(order_id)
    if not order:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)

    # Если методGet == qr (ATM) — восстановить лимит
    if order.methodGet == MethodGet.QR and order.bank:
        await lim_repo.update_amount(order.BankId, int(round(order.amountBuy)))

    cancelled = await order_repo.cancel(order_id)
    if not cancelled:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)
    await db.refresh(cancelled)
    return OrderOut.model_validate(cancelled)


async def close_order(db: AsyncSession, order_id: int) -> OrderOut:
    repo = OrderRepository(db)
    order = await repo.update_status(order_id, OrderStatus.COMPLETED)
    if not order:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)
    await db.refresh(order)
    return OrderOut.model_validate(order)
