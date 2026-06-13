"""Exchange flow handlers."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.core.database import create_db_session
from app.enums.country import Country
from app.exceptions import AntExException
from app.models.city import City
from app.repositories.order import OrderRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.services.exchange import (
    CANONICAL_SELL_CURRENCIES,
    COUNTRY_CURRENCY,
    ExchangePairSnapshot,
    ExchangeQuoteInput,
    ExchangeService,
)
from app.services.order_flow import create_order_for_user
from app.telegram import messages
from app.telegram.i18n import get_user_translator
from app.telegram.keyboards import (
    amount_controls,
    back_to_main_menu,
    choose_city,
    choose_country,
    choose_currency,
    choose_service,
    confirm_exchange,
)
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="exchange")
TOTAL_STEPS = 5
SERVICE_OPTIONS = {
    "cash_delivery": {
        "label_key": "btn-service-cash-delivery",
        "method": "cash",
        "needs_city": True,
    },
    "cash_atm": {
        "label_key": "btn-service-cash-atm",
        "method": "cash",
        "needs_city": False,
    },
    "bank_account": {
        "label_key": "btn-service-bank-account",
        "method": "qrcode",
        "needs_city": False,
    },
    "pay_services": {
        "label_key": "btn-service-pay-services",
        "method": "qrcode",
        "needs_city": False,
    },
}


class ExchangeState(StatesGroup):
    choosing_country = State()
    choosing_service = State()
    choosing_city = State()
    choosing_currency = State()
    entering_amount = State()
    choosing_method = State()
    confirming = State()


async def _get_db():
    return create_db_session()


async def _safe_edit_text(message, text: str, *, reply_markup) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _get_exchange_pairs(country: str | None = None) -> list[ExchangePairSnapshot]:
    try:
        db = await _get_db()
        async with db:
            snapshots = await ExchangeService().get_featured_pair_snapshots(db)
    except Exception:
        logger.exception("Ошибка при получении курсов обмена для Telegram: country=%s", country)
        return []

    if country is None:
        return snapshots

    try:
        selected_country = Country(country)
    except ValueError:
        return snapshots

    return [snapshot for snapshot in snapshots if snapshot.country == selected_country]


async def _render_step(
    *,
    actor,
    current: int,
    body: str,
    reply_markup,
    edit: bool,
    featured_pairs: list[ExchangePairSnapshot] | None = None,
) -> None:
    translate = get_user_translator(actor.from_user)
    if featured_pairs is None:
        featured_pairs = await _get_exchange_pairs()
    parts = [messages.exchange_step(current, TOTAL_STEPS, translator=translate)]
    if featured_pairs:
        parts.append(messages.exchange_pair_rates(featured_pairs, translator=translate))
    parts.append(body)
    text = "\n\n".join(parts)
    if edit:
        await _safe_edit_text(actor.message, text, reply_markup=reply_markup)
    else:
        await actor.answer(text, reply_markup=reply_markup)


def _format_method_label(method: str, translate) -> str:
    return {
        "qr": translate("btn-qr"),
        "qrcode": translate("btn-qr"),
        "rs": translate("btn-transfer"),
        "cash": translate("btn-cash"),
    }.get(method, method)


def _select_default_method(available_methods: list[str]) -> str:
    if "qrcode" in available_methods:
        return "qrcode"
    if available_methods:
        return available_methods[0]
    return "qrcode"


def _build_confirmation_text(*, translate, data: dict[str, object]) -> str:
    quote = data["quote"]
    method_label = data.get("service_label") or _format_method_label(data["method"], translate)
    return messages.exchange_confirm_summary(
        amount=data["amount_sell"],
        from_currency=data["currency_sell"],
        result=quote["amountBuy"],
        to_currency=data["currency_buy"],
        method=method_label,
        current=TOTAL_STEPS,
        total=TOTAL_STEPS,
        translator=translate,
    )


async def _show_confirmation(actor, state: FSMContext, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    data = await state.get_data()
    text = _build_confirmation_text(translate=translate, data=data)
    if edit:
        await _safe_edit_text(
            actor.message,
            text,
            reply_markup=confirm_exchange(translate),
        )
    else:
        await actor.answer(text, reply_markup=confirm_exchange(translate))


async def _show_country_step(actor, state: FSMContext, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    await state.clear()
    await state.set_state(ExchangeState.choosing_country)
    await _render_step(
        actor=actor,
        current=1,
        body=messages.choose_country_prompt(translator=translate),
        reply_markup=choose_country(translate),
        edit=edit,
        featured_pairs=[],
    )


async def _show_start_welcome(actor, state: FSMContext, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    await state.clear()
    await state.set_state(ExchangeState.choosing_country)
    text = messages.exchange_start_welcome(
        actor.from_user.first_name,
        locale=getattr(actor.from_user, "language_code", None),
    )
    if edit:
        await _safe_edit_text(actor.message, text, reply_markup=choose_country(translate))
    else:
        await actor.answer(text, reply_markup=choose_country(translate))


async def _show_country_fallback(
    actor,
    state: FSMContext,
    *,
    text: str,
    edit: bool,
) -> None:
    translate = get_user_translator(actor.from_user)
    await state.clear()
    await state.set_state(ExchangeState.choosing_country)
    if edit:
        await _safe_edit_text(
            actor.message,
            text,
            reply_markup=choose_country(translate),
        )
    else:
        await actor.answer(text, reply_markup=choose_country(translate))


async def _show_service_step(actor, state: FSMContext, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    data = await state.get_data()
    country = data.get("country")
    if not country:
        await _show_country_step(actor, state, edit=edit)
        return
    await state.set_state(ExchangeState.choosing_service)
    await _render_step(
        actor=actor,
        current=2,
        body=messages.choose_service_prompt(str(country), translator=translate),
        reply_markup=choose_service(translate),
        edit=edit,
        featured_pairs=[],
    )


async def _show_city_step(actor, state: FSMContext, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    data = await state.get_data()
    country = data.get("country")
    service_label = data.get("service_label", "")
    if not country:
        await _show_country_step(actor, state, edit=edit)
        return
    db = await _get_db()
    async with db:
        result = await db.execute(
            select(City).where(City.country == Country(str(country))).order_by(City.name)
        )
        cities = list(result.scalars().all())
    if not cities:
        await _show_currency_step(actor, state, edit=edit)
        return
    await state.set_state(ExchangeState.choosing_city)
    await _render_step(
        actor=actor,
        current=3,
        body=messages.choose_city_prompt(str(service_label), translator=translate),
        reply_markup=choose_city(translate, cities),
        edit=edit,
        featured_pairs=[],
    )


async def _show_currency_step(actor, state: FSMContext, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    data = await state.get_data()
    country = data.get("country")
    if not country:
        await _show_country_step(actor, state, edit=edit)
        return
    snapshots = await _get_exchange_pairs(str(country))
    supported_pairs = ExchangeService().build_supported_pairs(snapshots)
    if not supported_pairs:
        await _show_country_fallback(
            actor,
            state,
            text=messages.exchange_rate_unavailable(translator=translate),
            edit=edit,
        )
        return
    await state.set_state(ExchangeState.choosing_currency)
    await state.update_data(
        supported_pairs=supported_pairs,
        currency_buy=COUNTRY_CURRENCY.get(country, ""),
    )
    await _render_step(
        actor=actor,
        current=4,
        body=messages.choose_currency_prompt(translator=translate),
        reply_markup=choose_currency(translate, list(CANONICAL_SELL_CURRENCIES)),
        edit=edit,
        featured_pairs=snapshots,
    )


async def _show_orders(actor, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    db = await _get_db()
    async with db:
        user, created = await check_user(db, actor.from_user)
        if created:
            await db.commit()
        orders = await OrderRepository(db).get_user_orders(user.id)

    if not orders:
        text = messages.orders_empty(translator=translate)
    else:
        items = [
            messages.orders_item(
                order_id=getattr(order, "publicNumber", order.id),
                amount_sell=order.amountSell,
                currency_sell=order.currencySell,
                amount_buy=order.amountBuy,
                currency_buy=order.currencyBuy,
                translator=translate,
            )
            for order in orders
        ]
        text = "\n\n".join([messages.orders_header(translator=translate), *items])

    if edit:
        await _safe_edit_text(actor.message, text, reply_markup=back_to_main_menu(translate))
    else:
        await actor.answer(text, reply_markup=back_to_main_menu(translate))


async def _show_enter_amount_step(
    actor,
    state: FSMContext,
    *,
    edit: bool,
) -> None:
    translate = get_user_translator(actor.from_user)
    await state.set_state(ExchangeState.entering_amount)
    data = await state.get_data()
    await _render_step(
        actor=actor,
        current=5,
        body=messages.enter_amount_prompt(data["currency_sell"], translator=translate),
        reply_markup=amount_controls(translate),
        edit=edit,
    )


@router.callback_query(F.data == "menu:orders", ExchangeState.choosing_country)
async def menu_orders(callback: CallbackQuery) -> None:
    await _show_orders(callback, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:country:"), ExchangeState.choosing_country)
async def choose_exchange_country(callback: CallbackQuery, state: FSMContext) -> None:
    country = callback.data.rsplit(":", 1)[-1]  # type: ignore[union-attr]
    await state.update_data(country=country)
    await _show_service_step(callback, state, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:service:"), ExchangeState.choosing_service)
async def choose_exchange_service(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = callback.data.rsplit(":", 1)[-1]  # type: ignore[union-attr]
    translate = get_user_translator(callback.from_user)
    option = SERVICE_OPTIONS.get(service_id)
    if option is None:
        await callback.answer(
            messages.exchange_rate_unavailable(translator=translate),
            show_alert=True,
        )
        return
    await state.update_data(
        service=service_id,
        service_label=translate(option["label_key"]),
        method=option["method"],
        needs_city=option["needs_city"],
    )
    if option["needs_city"]:
        await _show_city_step(callback, state, edit=True)
    else:
        await _show_currency_step(callback, state, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:city:"), ExchangeState.choosing_city)
async def choose_exchange_city(callback: CallbackQuery, state: FSMContext) -> None:
    city_id = int(callback.data.rsplit(":", 1)[-1])  # type: ignore[union-attr]
    await state.update_data(city_id=city_id)
    await _show_currency_step(callback, state, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:currency:"), ExchangeState.choosing_currency)
async def choose_exchange_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.rsplit(":", 1)[-1]  # type: ignore[union-attr]
    await state.update_data(currency_sell=currency)
    await _show_enter_amount_step(callback, state, edit=True)
    await callback.answer()


@router.message(ExchangeState.entering_amount)
async def enter_amount(message: Message, state: FSMContext) -> None:
    translate = get_user_translator(message.from_user)
    try:
        amount = int((message.text or "").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            messages.invalid_amount(translator=translate),
            reply_markup=amount_controls(translate),
        )
        return

    await state.update_data(amount_sell=amount)
    data = await state.get_data()
    db = await _get_db()
    try:
        async with db:
            quote = await ExchangeService().get_quote(
                db,
                ExchangeQuoteInput(
                    currency_sell=data["currency_sell"],
                    currency_buy=data["currency_buy"],
                    amount_sell=amount,
                ),
            )
    except AntExException:
        await message.answer(
            messages.exchange_rate_unavailable(translator=translate),
            reply_markup=amount_controls(translate),
        )
        return

    methods = list(quote.available_methods)
    default_method = _select_default_method(methods)
    await state.update_data(
        available_methods=methods,
        method=default_method,
        quote=_quote_to_state_payload(quote),
    )
    await state.set_state(ExchangeState.confirming)
    await _show_confirmation(message, state, edit=False)


@router.callback_query(F.data.startswith("method:"), ExchangeState.choosing_method)
async def choose_method(callback: CallbackQuery, state: FSMContext) -> None:
    translate = get_user_translator(callback.from_user)
    method = callback.data.split(":")[1]  # type: ignore[union-attr]
    data = await state.get_data()
    db = await _get_db()
    async with db:
        quote = await ExchangeService().get_quote(
            db,
            ExchangeQuoteInput(
                currency_sell=data["currency_sell"],
                currency_buy=data["currency_buy"],
                amount_sell=data["amount_sell"],
            ),
        )
    if method not in quote.available_methods:
        await callback.answer(
            messages.exchange_rate_unavailable(translator=translate),
            show_alert=True,
        )
        return
    await state.update_data(method=method, quote=_quote_to_state_payload(quote))
    await state.set_state(ExchangeState.confirming)
    await _show_confirmation(callback, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "exchange:confirm", ExchangeState.confirming)
async def confirm_exchange_callback(callback: CallbackQuery, state: FSMContext) -> None:
    translate = get_user_translator(callback.from_user)
    data = await state.get_data()
    quote = data.get("quote")
    if not quote or quote.get("rate", 0) <= 0 or quote.get("amountBuy", 0) <= 0:
        await callback.answer(
            messages.exchange_rate_unavailable(translator=translate),
            show_alert=True,
        )
        return

    db = await _get_db()
    try:
        async with db:
            user, _ = await check_user(db, callback.from_user)
            country_value = data.get("country")
            if country_value is None:
                country_value = ExchangeService().infer_country_from_pair(
                    f"{data['currency_sell']}{data['currency_buy']}"
                ).value
            city_id = data.get("city_id")
            if city_id is None and data["method"] == "cash":
                city_id = getattr(user, "city_id", None)
            order = await create_order_for_user(
                db,
                user,
                MiniappOrderCreate(
                    cityId=city_id if data["method"] == "cash" else None,
                    country=Country(str(country_value)),
                    currencySell=data["currency_sell"],
                    amountSell=data["amount_sell"],
                    currencyBuy=data["currency_buy"],
                    amountBuy=quote["amountBuy"],
                    rate=quote["rate"],
                    methodGet=data["method"],
                ),
            )
    except AntExException as exc:
        await callback.answer(
            messages.order_creation_failed(
                code=getattr(exc, "code", None),
                translator=translate,
            ),
            show_alert=True,
        )
        return
    except Exception:
        logger.exception("Failed to create order in Telegram exchange flow")
        await callback.answer(
            messages.order_creation_failed(translator=translate),
            show_alert=True,
        )
        return

    await state.clear()
    await state.set_state(ExchangeState.choosing_country)
    await _safe_edit_text(
        callback.message,
        messages.order_created(
            getattr(order, "publicNumber", order.id),
            translator=translate,
        ),
        reply_markup=choose_country(translate),
    )
    await callback.answer()


@router.callback_query(F.data == "fsm:back")
async def fsm_back(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state == ExchangeState.choosing_method.state:
        await _show_enter_amount_step(callback, state, edit=True)
    elif current_state == ExchangeState.entering_amount.state:
        await _show_currency_step(callback, state, edit=True)
    elif current_state == ExchangeState.choosing_service.state:
        await _show_start_welcome(callback, state, edit=True)
    elif current_state == ExchangeState.confirming.state:
        await _show_enter_amount_step(callback, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "fsm:cancel")
async def fsm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_country_step(callback, state, edit=True)
    await callback.answer()


def _quote_to_state_payload(quote) -> dict[str, object]:
    return {
        "currencySell": quote.currency_sell,
        "currencyBuy": quote.currency_buy,
        "amountSell": quote.amount_sell,
        "amountBuy": quote.amount_buy,
        "rate": quote.rate,
    }
