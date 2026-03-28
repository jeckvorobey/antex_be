"""HTTP-роуты miniapp API."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbDep
from app.repositories.allowance import AllowanceRepository
from app.repositories.order import OrderRepository
from app.schemas.miniapp import (
    MiniappExchangeScreenResponse,
    MiniappHomeResponse,
    MiniappOrderCreate,
    MiniappOrderItem,
    MiniappOrdersResponse,
    MiniappProfileResponse,
    MiniappQuoteResponse,
)
from app.services.miniapp import (
    build_exchange_screen,
    build_home_response,
    build_orders_response,
    build_profile_response,
    calculate_quote,
    create_miniapp_order,
)
from app.services.rate import get_exchange_rates

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])


async def _load_rate_snapshot(db: DbDep) -> dict[str, float]:
    """Собирает единый snapshot курсов с учетом allowance."""
    allowance = await AllowanceRepository(db).get_value()
    return await get_exchange_rates(allowance)


@router.get("/home", response_model=MiniappHomeResponse)
async def get_home(db: DbDep, user: CurrentUser) -> MiniappHomeResponse:
    """Возвращает данные главного экрана miniapp."""
    snapshot = await _load_rate_snapshot(db)
    return build_home_response(user, snapshot)


@router.get("/exchange", response_model=MiniappExchangeScreenResponse)
async def get_exchange_screen(db: DbDep, _user: CurrentUser) -> MiniappExchangeScreenResponse:
    """Возвращает конфигурацию экрана обмена и стартовый quote."""
    snapshot = await _load_rate_snapshot(db)
    return build_exchange_screen(snapshot)


@router.get("/exchange/quote", response_model=MiniappQuoteResponse)
async def get_quote(
    db: DbDep,
    _user: CurrentUser,
    currency_sell: str = Query(..., alias="currencySell", min_length=3, max_length=10),
    currency_buy: str = Query(..., alias="currencyBuy", min_length=3, max_length=10),
    amount_sell: int = Query(..., alias="amountSell", gt=0),
) -> MiniappQuoteResponse:
    """Пересчитывает quote для выбранной валютной пары."""
    snapshot = await _load_rate_snapshot(db)
    return calculate_quote(snapshot, currency_sell.upper(), currency_buy.upper(), amount_sell)


@router.get("/orders", response_model=MiniappOrdersResponse)
async def get_orders(db: DbDep, user: CurrentUser) -> MiniappOrdersResponse:
    """Возвращает список заявок текущего пользователя для истории miniapp."""
    orders = await OrderRepository(db).get_user_orders(user.id)
    return build_orders_response(orders)


@router.post("/orders", response_model=MiniappOrderItem)
async def post_order(body: MiniappOrderCreate, db: DbDep, user: CurrentUser) -> MiniappOrderItem:
    """Создает заявку miniapp с серверным расчетом курса и суммы получения."""
    snapshot = await _load_rate_snapshot(db)
    order = await create_miniapp_order(db, user, body, snapshot)
    await db.commit()
    return order


@router.get("/profile", response_model=MiniappProfileResponse)
async def get_profile(user: CurrentUser) -> MiniappProfileResponse:
    """Возвращает профиль и вторичные действия для раздела profile."""
    return build_profile_response(user)
