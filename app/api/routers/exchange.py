"""Роутер обмена валют."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep
from app.repositories.allowance import AllowanceRepository
from app.repositories.order import OrderRepository
from app.schemas.order import OrderCreate, OrderOut, OrderUpdate
from app.schemas.rate import RatesResponse
from app.services import order as order_svc
from app.services.rate import get_exchange_rates

router = APIRouter(prefix="/api/exchange", tags=["exchange"])


@router.get("/rates", response_model=RatesResponse)
async def get_rates(db: DbDep) -> RatesResponse:
    allowance_repo = AllowanceRepository(db)
    allowance = await allowance_repo.get_value()
    data = await get_exchange_rates(allowance)
    return RatesResponse(
        rates=[],
        rubthb=data["RUBTHB"],
        allowance=data["allowance"],
    )


@router.post("/orders", response_model=OrderOut)
async def create_order(body: OrderCreate, db: DbDep, user: CurrentUser) -> OrderOut:
    return await order_svc.create_order(db, user.id, body)


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, db: DbDep, user: CurrentUser) -> OrderOut:
    from app.exceptions import AntExException
    repo = OrderRepository(db)
    order = await repo.get_one(order_id)
    if not order or order.UserId != user.id:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)
    return OrderOut.model_validate(order)


@router.put("/orders/{order_id}/status", response_model=OrderOut)
async def update_order_status(order_id: int, body: OrderUpdate, db: DbDep, user: CurrentUser) -> OrderOut:
    from app.exceptions import AntExException
    repo = OrderRepository(db)
    order = await repo.get_one(order_id)
    if not order or order.UserId != user.id:
        raise AntExException("Order not found", code="ORDER_NOT_FOUND", status_code=404)
    if body.status:
        updated = await repo.update_status(order_id, body.status)
        return OrderOut.model_validate(updated)
    return OrderOut.model_validate(order)
