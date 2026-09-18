"""Роутер заявок пользователя."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbDep
from app.enums.order import OrderStatus
from app.models.order import Order
from app.models.user import User
from app.repositories.order import OrderRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.schemas.order import OrderCreate, OrderOut, build_order_out
from app.services.order_flow import create_order_for_user
from app.services.order_status import update_order_status

router = APIRouter(prefix="/api/orders", tags=["orders"])

# Пользователь может отменить только свою заявку в статусе "Создана".
_USER_CANCELLABLE_STATUSES: frozenset[OrderStatus] = frozenset({OrderStatus.CREATED})


@router.get("", response_model=list[OrderOut])
async def list_my_orders(
    db: DbDep,
    user: CurrentUser,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[OrderOut]:
    repo = OrderRepository(db)
    return [
        build_order_out(order)
        for order in await repo.get_user_orders(user.id, limit=limit, offset=offset)
    ]


@router.get("/{order_id}", response_model=OrderOut)
async def get_my_order(order_id: int, db: DbDep, user: CurrentUser) -> OrderOut:
    repo = OrderRepository(db)
    order = await repo.get_one(order_id)
    if not order or order.UserId != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return build_order_out(order)


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(body: OrderCreate, db: DbDep, user: CurrentUser) -> OrderOut:
    payload = MiniappOrderCreate(
        cityId=body.CityId,
        country=body.country,
        currencySell=body.currencySell,
        amountSell=body.amountSell,
        currencyBuy=body.currencyBuy,
        amountBuy=body.amountBuy,
        rate=body.rate,
        methodGet=body.methodGet,
    )
    order = await create_order_for_user(db, user, payload)
    return build_order_out(order)


@router.post("/{order_id}/cancel", response_model=OrderOut)
async def cancel_my_order(order_id: int, db: DbDep, user: CurrentUser) -> OrderOut:
    repo = OrderRepository(db)
    order = await repo.get_one(order_id)
    if not order or order.UserId != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    await update_order_status(
        db,
        order_id=order_id,
        status=OrderStatus.CANCELLED,
        manager_id=None,
        allowed_source_statuses=_USER_CANCELLABLE_STATUSES,
    )
    # Перечитать заявку заново, подтянув полную цепочку eager-loading:
    # после смены статуса связи встроенного user (User.city и др.)
    # не гарантируют загруженность.
    refreshed = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.destroyTime.is_(None))
        .options(
            selectinload(Order.user).selectinload(User.city),
            selectinload(Order.city),
        )
        .execution_options(populate_existing=True)
    )
    refreshed_order = refreshed.scalar_one_or_none()
    if refreshed_order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return build_order_out(refreshed_order)
