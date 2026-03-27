"""Обработчики flow обмена валют."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.core.database import get_db_session
from app.repositories.allowance import AllowanceRepository
from app.repositories.bank import BankRepository
from app.telegram import messages
from app.telegram.keyboards import home, menu, obtaining
from app.telegram.services.notification_service import notify_operator
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="exchange")


class ExchangeState(StatesGroup):
    choosing_currency = State()
    entering_amount = State()
    choosing_method = State()
    confirming = State()


@router.message(F.text.in_(["💱 Обмен", "🇷🇺 RUB → THB", "💎 USDT → THB"]))
async def start_exchange(message: Message, state: FSMContext) -> None:
    currency = "USDT" if "USDT" in (message.text or "") else "RUB"
    await state.update_data(currency_sell=currency)
    await state.set_state(ExchangeState.entering_amount)
    await message.answer(messages.enter_amount(currency), reply_markup=menu())


@router.message(ExchangeState.entering_amount)
async def enter_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = int(message.text or "")
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(messages.invalid_amount())
        return

    await state.update_data(amount_sell=amount)
    await state.set_state(ExchangeState.choosing_method)
    await message.answer("Выберите способ получения THB:", reply_markup=obtaining())


@router.callback_query(F.data.startswith("method:"), ExchangeState.choosing_method)
async def choose_method(callback: CallbackQuery, state: FSMContext) -> None:
    method = callback.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(method=method)

    data = await state.get_data()
    currency_sell = data["currency_sell"]
    amount_sell = data["amount_sell"]

    db_gen = get_db_session()
    db = await db_gen.__anext__()
    async with db:
        allowance_repo = AllowanceRepository(db)
        allowance = await allowance_repo.get_value()

        from app.services.rate import get_exchange_rates
        rates = await get_exchange_rates(allowance)
        rubthb = rates["RUBTHB"]

        amount_buy = int(amount_sell / rubthb) if currency_sell == "RUB" else int(amount_sell * rubthb)
        await state.update_data(amount_buy=amount_buy, rate=rubthb)

        bank_repo = BankRepository(db)
        banks = await bank_repo.get_all()

    await state.set_state(ExchangeState.confirming)
    await callback.message.answer(  # type: ignore[union-attr]
        f"📋 <b>Подтвердите заявку</b>\n\n"
        f"Отдаёте: <b>{amount_sell:,} {currency_sell}</b>\n"
        f"Получаете: <b>{amount_buy:,} THB</b>\n"
        f"Способ: <b>{method}</b>",
    )
    await callback.answer()


@router.callback_query(F.data == "exchange:confirm", ExchangeState.confirming)
async def confirm_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    db_gen = get_db_session()
    db = await db_gen.__anext__()
    async with db:
        user, _ = await check_user(db, callback.from_user)
        bank_repo = BankRepository(db)
        banks = await bank_repo.get_all()
        bank = banks[0] if banks else None
        if not bank:
            await callback.answer("Нет доступных банков", show_alert=True)
            return

        from app.repositories.order import OrderRepository
        order_repo = OrderRepository(db)
        order = await order_repo.create(
            UserId=user.id,
            BankId=bank.id,
            currencySell=data["currency_sell"],
            amountSell=data["amount_sell"],
            currencyBuy="THB",
            amountBuy=data["amount_buy"],
            rate=data["rate"],
            methodGet=data["method"],
            status=1,
        )
        await db.commit()

    await state.clear()
    await callback.message.answer(  # type: ignore[union-attr]
        messages.order_created(order.id, order.amountSell, order.currencySell, order.amountBuy, order.currencyBuy),
        reply_markup=home(),
    )
    await notify_operator(
        callback.bot, order.id, user.id,
        order.amountSell, order.currencySell,
        order.amountBuy, order.currencyBuy,
        data["method"],
    )
    await callback.answer()


@router.message(F.text == "🏠 Главная")
async def go_home(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню", reply_markup=home())
