"""Роутер заявок пользователя."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbDep
from app.repositories.order import OrderRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.schemas.order import OrderCreate, OrderOut, build_order_out
from app.services.order_flow import create_order_for_user

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
async def list_my_orders(db: DbDep, user: CurrentUser) -> list[OrderOut]:
    repo = OrderRepository(db)
    return [build_order_out(order) for order in await repo.get_user_orders(user.id, limit=100)]


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
        currencySell=body.currencySell,
        amountSell=body.amountSell,
        currencyBuy=body.currencyBuy,
        amountBuy=body.amountBuy,
        rate=body.rate,
        address=body.address,
        contactTelegram=body.contactTelegram,
        methodGet=body.methodGet,
    )
    order = await create_order_for_user(db, user, payload)
    return build_order_out(order)
