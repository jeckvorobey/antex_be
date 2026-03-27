"""Exchange flow handlers."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.core.config import settings
from app.core.database import get_db_session
from app.enums.order import OrderStatus
from app.repositories.allowance import AllowanceRepository
from app.repositories.bank import BankRepository
from app.repositories.order import OrderRepository
from app.telegram import messages
from app.telegram.i18n import get_user_translator
from app.telegram.keyboards import choose_currency, confirm_exchange, home, obtaining
from app.telegram.services.notification_service import notify_operator
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="exchange")
TOTAL_STEPS = 4


class ExchangeState(StatesGroup):
    choosing_currency = State()
    entering_amount = State()
    choosing_method = State()
    confirming = State()


async def _get_db():
    async for session in get_db_session():
        return session
    raise RuntimeError("Database session is unavailable")


async def _get_rate_snapshot() -> tuple[float, float]:
    allowance = settings.default_allowance
    try:
        db = await _get_db()
        async with db:
            allowance = await AllowanceRepository(db).get_value()
    except Exception:
        logger.exception("Failed to load allowance for Telegram exchange flow")

    try:
        from app.services.rate import get_exchange_rates

        rates = await get_exchange_rates(allowance)
        return rates["RUBTHB"], rates["USDTTHB"]
    except Exception:
        logger.exception("Failed to load exchange rates for Telegram exchange flow")
        return 0.0, 0.0


async def _render_step(
    *,
    actor,
    current: int,
    body: str,
    reply_markup,
    edit: bool,
) -> None:
    translate = get_user_translator(actor.from_user)
    rubthb, usdtthb = await _get_rate_snapshot()
    text = "\n".join(
        [
            messages.exchange_step(current, TOTAL_STEPS, translator=translate),
            messages.exchange_rate(rubthb, usdtthb, translator=translate),
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


def _calculate_amount_buy(amount_sell: int, currency_sell: str, rubthb: float) -> int:
    if rubthb <= 0:
        return 0
    if currency_sell == "RUB":
        return int(amount_sell / rubthb)
    return int(amount_sell * rubthb)


async def show_confirmation(callback: CallbackQuery, state: FSMContext) -> None:
    translate = get_user_translator(callback.from_user)
    data = await state.get_data()
    text = messages.exchange_confirm_summary(
        amount=data["amount_sell"],
        from_currency=data["currency_sell"],
        result=data["amount_buy"],
        to_currency="THB",
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
    await state.clear()
    await state.set_state(ExchangeState.choosing_currency)
    await _render_step(
        actor=actor,
        current=1,
        body=messages.choose_currency_prompt(translator=translate),
        reply_markup=choose_currency(translate),
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
    currency: str,
    *,
    edit: bool,
) -> None:
    translate = get_user_translator(actor.from_user)
    await state.update_data(currency_sell=currency)
    await state.set_state(ExchangeState.entering_amount)
    await _render_step(
        actor=actor,
        current=2,
        body=messages.enter_amount_prompt(currency, translator=translate),
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
    await _show_enter_amount_step(callback, state, currency, edit=True)
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
    await state.set_state(ExchangeState.choosing_method)
    await _render_step(
        actor=message,
        current=3,
        body=messages.choose_method_prompt("THB", translator=translate),
        reply_markup=obtaining(translate),
        edit=False,
    )


@router.callback_query(F.data.startswith("method:"), ExchangeState.choosing_method)
async def choose_method(callback: CallbackQuery, state: FSMContext) -> None:
    translate = get_user_translator(callback.from_user)
    method = callback.data.split(":")[1]  # type: ignore[union-attr]
    data = await state.get_data()
    rubthb, _ = await _get_rate_snapshot()
    amount_buy = _calculate_amount_buy(data["amount_sell"], data["currency_sell"], rubthb)
    if rubthb <= 0 or amount_buy <= 0:
        await callback.answer(
            messages.exchange_rate_unavailable(translator=translate),
            show_alert=True,
        )
        return
    await state.update_data(method=method, amount_buy=amount_buy, rate=rubthb)
    await state.set_state(ExchangeState.confirming)
    await show_confirmation(callback, state)


@router.callback_query(F.data == "exchange:confirm", ExchangeState.confirming)
async def confirm_exchange_callback(callback: CallbackQuery, state: FSMContext) -> None:
    translate = get_user_translator(callback.from_user)
    data = await state.get_data()
    if data.get("rate", 0) <= 0 or data.get("amount_buy", 0) <= 0:
        await callback.answer(
            messages.exchange_rate_unavailable(translator=translate),
            show_alert=True,
        )
        return

    db = await _get_db()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        bank = next(iter(await BankRepository(db).get_all()), None)
        if bank is None:
            await callback.answer("No bank available", show_alert=True)
            return

        order = await OrderRepository(db).create(
            UserId=user.id,
            BankId=bank.id,
            currencySell=data["currency_sell"],
            amountSell=data["amount_sell"],
            currencyBuy="THB",
            amountBuy=data["amount_buy"],
            rate=data["rate"],
            methodGet=data["method"],
            status=OrderStatus.NEW,
        )
        await db.commit()

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
    await notify_operator(
        callback.bot,
        order.id,
        user.id,
        order.amountSell,
        order.currencySell,
        order.amountBuy,
        order.currencyBuy,
        data["method"],
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
            current=2,
            body=messages.enter_amount_prompt(
                data.get("currency_sell", "THB"),
                translator=translate,
            ),
            reply_markup=home(translate),
            edit=True,
        )
    elif current_state == ExchangeState.confirming.state:
        await state.set_state(ExchangeState.choosing_method)
        await _render_step(
            actor=callback,
            current=3,
            body=messages.choose_method_prompt("THB", translator=translate),
            reply_markup=obtaining(translate),
            edit=True,
        )
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


@router.message(F.text.in_(["🇷🇺 RUB → THB", "💎 USDT → THB"]))
async def legacy_choose_currency(message: Message, state: FSMContext) -> None:
    currency = "USDT" if "USDT" in (message.text or "") else "RUB"
    await _show_enter_amount_step(message, state, currency, edit=False)


@router.message(F.text == "🏠 Главная")
async def legacy_home(message: Message, state: FSMContext) -> None:
    await _show_home(message, state, edit=False)
