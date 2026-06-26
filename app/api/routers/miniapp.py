"""Miniapp API на новой схеме."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import DbDep, MiniappUser
from app.schemas.aex import ReferralApplyRequest, ReferralApplyResponse
from app.schemas.miniapp import (
    MiniappAexReferralResponse,
    MiniappCitiesResponse,
    MiniappExchangeScreenResponse,
    MiniappHomeResponse,
    MiniappOrderCreate,
    MiniappOrderItem,
    MiniappOrdersResponse,
    MiniappProfileScreenResponse,
    MiniappQuoteResponse,
    MiniappRatesResponse,
    build_miniapp_order_item,
)
from app.services.miniapp import (
    calculate_miniapp_quote,
    get_miniapp_aex_referral,
    get_miniapp_exchange,
    get_miniapp_home,
    get_miniapp_profile_screen,
    list_miniapp_cities,
    list_miniapp_orders,
    list_miniapp_rates,
)
from app.services.order_flow import create_order_for_user
from app.services.referral import ReferralService

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])


@router.get("/home", response_model=MiniappHomeResponse)
async def get_home(db: DbDep, user: MiniappUser) -> MiniappHomeResponse:
    return await get_miniapp_home(db, user)


@router.get("/exchange", response_model=MiniappExchangeScreenResponse)
async def get_exchange(db: DbDep, _: MiniappUser) -> MiniappExchangeScreenResponse:
    return await get_miniapp_exchange(db)


@router.get("/exchange/quote", response_model=MiniappQuoteResponse)
async def get_exchange_quote(
    db: DbDep,
    _: MiniappUser,
    currency_sell: str = Query(alias="currencySell", min_length=3, max_length=20),
    currency_buy: str = Query(alias="currencyBuy", min_length=3, max_length=20),
    amount_sell: int = Query(alias="amountSell", gt=0),
) -> MiniappQuoteResponse:
    return await calculate_miniapp_quote(db, currency_sell, currency_buy, amount_sell)


@router.get("/cities", response_model=MiniappCitiesResponse)
async def get_cities(db: DbDep, _: MiniappUser) -> MiniappCitiesResponse:
    return await list_miniapp_cities(db)


@router.get("/rates", response_model=MiniappRatesResponse)
async def get_rates(db: DbDep, _: MiniappUser) -> MiniappRatesResponse:
    return await list_miniapp_rates(db)


@router.get("/orders", response_model=MiniappOrdersResponse)
async def get_orders(
    db: DbDep,
    user: MiniappUser,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MiniappOrdersResponse:
    return await list_miniapp_orders(db, user.id, limit=limit, offset=offset)


@router.post(
    "/orders",
    response_model=MiniappOrderItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    body: MiniappOrderCreate,
    db: DbDep,
    user: MiniappUser,
) -> MiniappOrderItem:
    order = await create_order_for_user(db, user, body)
    return build_miniapp_order_item(order)


@router.get("/profile", response_model=MiniappProfileScreenResponse)
async def get_profile(db: DbDep, user: MiniappUser) -> MiniappProfileScreenResponse:
    return await get_miniapp_profile_screen(db, user)


@router.get("/aex/referral", response_model=MiniappAexReferralResponse)
async def get_aex_referral(db: DbDep, user: MiniappUser) -> MiniappAexReferralResponse:
    return await get_miniapp_aex_referral(db, user)


@router.post("/aex/referral/apply", response_model=ReferralApplyResponse)
async def apply_aex_referral(
    body: ReferralApplyRequest,
    db: DbDep,
    user: MiniappUser,
) -> ReferralApplyResponse:
    """Применить referral deep-link один раз при первом входе miniapp."""
    await ReferralService().bind_referral(db, user, body.code)
    await db.commit()
    return ReferralApplyResponse(success=True)
