"""Exchange flow handlers."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.core.database import get_db_session
from app.repositories.order import OrderRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.services.exchange import ExchangePairSnapshot, ExchangeQuoteInput, ExchangeService
from app.services.order_flow import create_order_for_user
from app.telegram import messages
from app.telegram.i18n import get_user_translator
from app.telegram.keyboards import (
    choose_buy_currency,
    choose_currency,
    confirm_exchange,
    home,
    obtaining,
)
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="exchange")
TOTAL_STEPS = 5


class ExchangeState(StatesGroup):
    choosing_currency = State()
    choosing_buy_currency = State()
    entering_amount = State()
    choosing_method = State()
    confirming = State()


async def _get_db():
    async for session in get_db_session():
        return session
    raise RuntimeError("Database session is unavailable")


async def _get_exchange_pairs() -> list[ExchangePairSnapshot]:
    try:
        db = await _get_db()
        async with db:
            return await ExchangeService().get_featured_pair_snapshots(db)
    except Exception:
        logger.exception("Failed to load exchange rates for Telegram exchange flow")
        return []


async def _render_step(
    *,
    actor,
    current: int,
    body: str,
    reply_markup,
    edit: bool,
) -> None:
    translate = get_user_translator(actor.from_user)
    featured_pairs = await _get_exchange_pairs()
    text = "\n".join(
        [
            messages.exchange_step(current, TOTAL_STEPS, translator=translate),
            messages.exchange_pair_rates(featured_pairs[:3], translator=translate),
            body,
        ]
    )
    if edit:
        await actor.message.edit_text(text, reply_markup=reply_markup)
    else:
        await actor.answer(text, reply_markup=reply_markup)


def _format_method_label(method: str, translate) -> str:
    return {
        "qr": translate("btn-qr"),
        "rs": translate("btn-transfer"),
        "cash": translate("btn-cash"),
    }.get(method, method)


async def show_confirmation(callback: CallbackQuery, state: FSMContext) -> None:
    translate = get_user_translator(callback.from_user)
    data = await state.get_data()
    quote = data["quote"]
    text = messages.exchange_confirm_summary(
        amount=data["amount_sell"],
        from_currency=data["currency_sell"],
        result=quote["amountBuy"],
        to_currency=data["currency_buy"],
        method=_format_method_label(data["method"], translate),
        translator=translate,
    )
    await callback.message.edit_text(
        text,
        reply_markup=confirm_exchange(translate),
    )
    await callback.answer()


async def _show_exchange_menu(actor, state: FSMContext, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    db = await _get_db()
    async with db:
        snapshots = await ExchangeService().list_pair_snapshots(db)
    supported_pairs = ExchangeService().build_supported_pairs(snapshots)
    await state.clear()
    await state.set_state(ExchangeState.choosing_currency)
    await state.update_data(supported_pairs=supported_pairs)
    await _render_step(
        actor=actor,
        current=1,
        body=messages.choose_currency_prompt(translator=translate),
        reply_markup=choose_currency(translate, list(supported_pairs)),
        edit=edit,
    )


async def _show_orders(actor, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    db = await _get_db()
    async with db:
        user, _ = await check_user(db, actor.from_user)
        orders = await OrderRepository(db).get_user_orders(user.id)

    if not orders:
        text = messages.orders_empty(translator=translate)
    else:
        items = [
            messages.orders_item(
                order_id=order.id,
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
        await actor.message.edit_text(text, reply_markup=home(translate))
    else:
        await actor.answer(text, reply_markup=home(translate))


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
        current=3,
        body=messages.enter_amount_prompt(data["currency_sell"], translator=translate),
        reply_markup=home(translate),
        edit=edit,
    )


async def _show_home(actor, state: FSMContext, *, edit: bool) -> None:
    translate = get_user_translator(actor.from_user)
    await state.clear()
    if edit:
        await actor.message.edit_text(
            messages.home_title(translator=translate),
            reply_markup=home(translate),
        )
    else:
        await actor.answer(
            messages.home_title(translator=translate),
            reply_markup=home(translate),
        )


@router.callback_query(F.data == "menu:exchange")
async def menu_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_exchange_menu(callback, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "menu:orders")
async def menu_orders(callback: CallbackQuery) -> None:
    await _show_orders(callback, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:currency:"), ExchangeState.choosing_currency)
async def choose_exchange_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.rsplit(":", 1)[-1]  # type: ignore[union-attr]
    data = await state.get_data()
    supported_pairs = data.get("supported_pairs", {})
    buy_currencies = supported_pairs.get(currency, [])
    translate = get_user_translator(callback.from_user)
    await state.update_data(currency_sell=currency)
    await state.set_state(ExchangeState.choosing_buy_currency)
    await _render_step(
        actor=callback,
        current=2,
        body=messages.choose_buy_currency_prompt(currency, translator=translate),
        reply_markup=choose_buy_currency(translate, buy_currencies),
        edit=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:buy:"), ExchangeState.choosing_buy_currency)
async def choose_exchange_buy_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.rsplit(":", 1)[-1]  # type: ignore[union-attr]
    await state.update_data(currency_buy=currency)
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
            reply_markup=home(translate),
        )
        return

    await state.update_data(amount_sell=amount)
    data = await state.get_data()
    methods = ExchangeService().get_methods_for_currency(data["currency_buy"])
    await state.update_data(available_methods=methods)
    await state.set_state(ExchangeState.choosing_method)
    await _render_step(
        actor=message,
        current=4,
        body=messages.choose_method_prompt(data["currency_buy"], translator=translate),
        reply_markup=obtaining(translate, methods),
        edit=False,
    )


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
    await show_confirmation(callback, state)


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
    async with db:
        user, _ = await check_user(db, callback.from_user)
        order = await create_order_for_user(
            db,
            user,
            MiniappOrderCreate(
                cityId=user.city_id if data["method"] == "cash" else None,
                country=ExchangeService().infer_country_from_pair(
                    f"{data['currency_sell']}{data['currency_buy']}"
                ),
                currencySell=data["currency_sell"],
                amountSell=data["amount_sell"],
                currencyBuy=data["currency_buy"],
                methodGet=data["method"],
            ),
        )

    await state.clear()
    await callback.message.edit_text(
        messages.order_created(
            order.id,
            order.amountSell,
            order.currencySell,
            order.amountBuy,
            order.currencyBuy,
            translator=translate,
        ),
        reply_markup=home(translate),
    )
    await callback.answer()


@router.callback_query(F.data == "fsm:back")
async def fsm_back(callback: CallbackQuery, state: FSMContext) -> None:
    translate = get_user_translator(callback.from_user)
    current_state = await state.get_state()
    data = await state.get_data()
    if current_state == ExchangeState.choosing_method.state:
        await state.set_state(ExchangeState.entering_amount)
        await _render_step(
            actor=callback,
            current=3,
            body=messages.enter_amount_prompt(
                data.get("currency_sell", "RUB"),
                translator=translate,
            ),
            reply_markup=home(translate),
            edit=True,
        )
    elif current_state == ExchangeState.entering_amount.state:
        await state.set_state(ExchangeState.choosing_buy_currency)
        await _render_step(
            actor=callback,
            current=2,
            body=messages.choose_buy_currency_prompt(
                data.get("currency_sell", "RUB"),
                translator=translate,
            ),
            reply_markup=choose_buy_currency(
                translate,
                data.get("supported_pairs", {}).get(data.get("currency_sell", "RUB"), []),
            ),
            edit=True,
        )
    elif current_state == ExchangeState.confirming.state:
        await state.set_state(ExchangeState.choosing_method)
        await _render_step(
            actor=callback,
            current=4,
            body=messages.choose_method_prompt(
                data.get("currency_buy", "THB"),
                translator=translate,
            ),
            reply_markup=obtaining(translate, data.get("available_methods", ["cash"])),
            edit=True,
        )
    elif current_state == ExchangeState.choosing_buy_currency.state:
        await _show_exchange_menu(callback, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "fsm:cancel")
async def fsm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_home(callback, state, edit=True)
    await callback.answer()


@router.message(F.text == "💱 Обмен")
async def legacy_menu_exchange(message: Message, state: FSMContext) -> None:
    await _show_exchange_menu(message, state, edit=False)


@router.message(F.text == "📋 Мои заявки")
async def legacy_menu_orders(message: Message) -> None:
    await _show_orders(message, edit=False)


@router.message(F.text == "🏠 Главная")
async def legacy_home(message: Message, state: FSMContext) -> None:
    await _show_home(message, state, edit=False)


def _quote_to_state_payload(quote) -> dict[str, object]:
    return {
        "currencySell": quote.currency_sell,
        "currencyBuy": quote.currency_buy,
        "amountSell": quote.amount_sell,
        "amountBuy": quote.amount_buy,
        "rate": quote.rate,
    }
