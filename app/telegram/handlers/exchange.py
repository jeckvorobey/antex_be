"""Exchange flow handlers."""

from __future__ import annotations

import logging
from typing import cast

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import create_db_session
from app.enums.country import Country
from app.exceptions import AntExException
from app.models.city import City
from app.repositories.city import CityRepository
from app.repositories.config import ConfigRepository
from app.repositories.order import OrderRepository
from app.schemas.miniapp import MiniappOrderCreate
from app.services.exchange import (
    CANONICAL_SELL_CURRENCIES,
    COUNTRY_CURRENCY,
    ExchangePairSnapshot,
    ExchangeQuoteInput,
    ExchangeService,
)
from app.services.manager_working_hours import ManagerWorkingHoursService
from app.services.order_flow import create_order_for_user, get_min_amount
from app.telegram import messages
from app.telegram.i18n import get_user_translator
from app.telegram.keyboards import (
    amount_controls,
    choose_city,
    choose_country,
    choose_currency,
    choose_service,
    confirm_exchange,
    order_created_actions,
    orders_pagination,
)
from app.telegram.services.user_service import check_user

logger = logging.getLogger(__name__)
router = Router(name="exchange")
TOTAL_STEPS = 5
ORDERS_PAGE_SIZE = 10
SERVICE_OPTIONS = {
    "cash_delivery": {
        "label_key": "btn-service-cash-delivery",
        "method": "cash",
        "needs_city": True,
    },
    "cash_atm": {
        "label_key": "btn-service-cash-atm",
        "method": "qrcode",
        "needs_city": False,
    },
    "bank_account": {
        "label_key": "btn-service-bank-account",
        "method": "bank_account",
        "needs_city": False,
    },
    "pay_services": {
        "label_key": "btn-service-pay-services",
        "method": "pay_services",
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


async def _safe_delete_message(message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest as exc:
        if "message to delete not found" not in str(exc).lower():
            raise


async def _safe_delete_chat_message(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest as exc:
        if "message to delete not found" not in str(exc).lower():
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
        "cash": translate("btn-service-cash-delivery"),
        "bank_account": translate("btn-service-bank-account"),
        "pay_services": translate("btn-service-pay-services"),
    }.get(method, method)


def _select_default_method(available_methods: list[str]) -> str:
    if "qrcode" in available_methods:
        return "qrcode"
    if available_methods:
        return available_methods[0]
    return "qrcode"


def _build_confirmation_text(*, translate, data: dict[str, object]) -> str:
    quote = cast(dict[str, object], data["quote"])
    amount_sell = cast(int, data["amount_sell"])
    currency_sell = cast(str, data["currency_sell"])
    currency_buy = cast(str, data["currency_buy"])
    method = cast(str, data["method"])
    method_label = cast(str, data.get("service_label") or _format_method_label(method, translate))
    country_value = data.get("country")
    try:
        country_label = (
            Country(str(country_value)).ru_name if country_value is not None else str(country_value)
        )
    except ValueError:
        country_label = str(country_value)
    city_label = cast(str | None, data.get("city_name"))
    return messages.exchange_confirm_summary(
        country=country_label,
        rate=str(quote.get("rateText") or quote.get("rate") or ""),
        amount=amount_sell,
        from_currency=currency_sell,
        result=cast(int | float, quote["amountBuy"]),
        to_currency=currency_buy,
        method=method_label,
        city=city_label,
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
    business_hours_text = None
    try:
        db = await _get_db()
        async with db:
            config = await ConfigRepository(db).get_or_create()
        availability = ManagerWorkingHoursService().get_availability(config)
        if availability.schedule_enabled:
            business_hours_text = ManagerWorkingHoursService().format_business_hours(
                availability.working_days_utc,
                availability.start_time_utc,
                availability.end_time_utc,
                locale=getattr(actor.from_user, "language_code", None),
            )
    except SQLAlchemyError:
        logger.warning("Не удалось загрузить график менеджеров для Telegram-приветствия")  # noqa: RUF001
    text = messages.exchange_start_welcome(
        actor.from_user.first_name,
        locale=getattr(actor.from_user, "language_code", None),
        business_hours_text=business_hours_text,
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
    current_data = await state.get_data()
    clean_data = {k: v for k, v in current_data.items() if k != "pair_snapshots"}
    clean_data.update(
        {
            "supported_pairs": supported_pairs,
            "currency_buy": COUNTRY_CURRENCY.get(country, ""),
        }
    )
    await state.clear()
    await state.set_state(ExchangeState.choosing_currency)
    await state.update_data(**clean_data)
    canonical_sell_currencies = [
        currency for currency in ("USDT", "RUB") if currency in CANONICAL_SELL_CURRENCIES
    ]
    await _render_step(
        actor=actor,
        current=4,
        body=messages.choose_currency_prompt(translator=translate),
        reply_markup=choose_currency(translate, canonical_sell_currencies),
        edit=edit,
        featured_pairs=snapshots,
    )


async def _show_orders(actor, *, edit: bool, page: int = 1) -> None:
    translate = get_user_translator(actor.from_user)
    safe_page = max(1, page)
    offset = (safe_page - 1) * ORDERS_PAGE_SIZE
    db = await _get_db()
    async with db:
        user, created = await check_user(db, actor.from_user)
        if created:
            await db.commit()
        repository = OrderRepository(db)
        total = await repository.count_user_orders(user.id)
        orders = await repository.get_user_orders(
            user.id,
            limit=ORDERS_PAGE_SIZE,
            offset=offset,
        )

    if total and not orders and safe_page > 1:
        return await _show_orders(actor, edit=edit, page=1)

    if not orders:
        text = messages.orders_empty(translator=translate)
    else:
        items = [
            messages.orders_item(
                order_id=getattr(order, "publicNumber", order.id),
                status=getattr(order, "status", None),
                amount_sell=order.amountSell,
                currency_sell=order.currencySell,
                amount_buy=order.amountBuy,
                currency_buy=order.currencyBuy,
                rate=getattr(order, "rate", None),
                method=getattr(order, "methodGet", None),
                created_at=getattr(order, "createdAt", None),
                updated_at=getattr(order, "updatedAt", None),
                end_time=getattr(order, "endTime", None),
                translator=translate,
            )
            for order in orders
        ]
        text = "\n\n".join([messages.orders_header(translator=translate), *items])

    reply_markup = orders_pagination(
        translate,
        page=safe_page,
        total=total,
        page_size=ORDERS_PAGE_SIZE,
    )
    if edit:
        await _safe_edit_text(actor.message, text, reply_markup=reply_markup)
    else:
        await actor.answer(text, reply_markup=reply_markup)


async def _show_enter_amount_step(
    actor,
    state: FSMContext,
    *,
    edit: bool,
) -> None:
    translate = get_user_translator(actor.from_user)
    await state.set_state(ExchangeState.entering_amount)
    data = await state.get_data()
    snapshots = await _get_exchange_pairs(str(data["country"])) if data.get("country") else []
    current_sell = data.get("currency_sell")
    current_buy = data.get("currency_buy")
    await state.update_data(amount_prompt_message_id=getattr(actor.message, "message_id", None))
    featured_pairs = [
        pair
        for pair in snapshots
        if getattr(pair, "currency_sell", None) == current_sell
        and getattr(pair, "currency_buy", None) == current_buy
    ]
    if not featured_pairs and data.get("country"):
        db = await _get_db()
        service = ExchangeService()
        async with db:
            rates = await service.load_rates(db)
        try:
            selected_country = Country(str(data["country"]))
            quote = service.build_quote(
                rates,
                ExchangeQuoteInput(
                    currency_sell=str(current_sell),
                    currency_buy=str(current_buy),
                    amount_sell=1,
                ),
            )
        except Exception:
            featured_pairs = []
        else:
            featured_pairs = [
                ExchangePairSnapshot(
                    pair_id=f"{quote.currency_sell.lower()}-{quote.currency_buy.lower()}",
                    label=f"{quote.currency_sell}/{quote.currency_buy}",
                    currency_sell=quote.currency_sell,
                    currency_buy=quote.currency_buy,
                    country=selected_country,
                    base_rate=quote.rate,
                    client_rate=quote.rate,
                    calculation_rate=quote.rate,
                    rate_display=quote.rate_display,
                    rate_text=quote.rate_text,
                    amount_sell_example=quote.amount_sell,
                    amount_buy_example=quote.amount_buy,
                    updated_at=quote.updated_at,
                    available_methods=quote.available_methods,
                )
            ]
    min_amount = get_min_amount(str(data.get("method", "")), str(data["currency_sell"]))
    await _render_step(
        actor=actor,
        current=5,
        body=messages.enter_amount_prompt(
            str(data["currency_sell"]),
            min_amount=min_amount,
            translator=translate,
        ),
        reply_markup=amount_controls(translate),
        edit=edit,
        featured_pairs=featured_pairs,
    )


@router.callback_query(F.data == "menu:orders", ExchangeState.choosing_country)
async def menu_orders(callback: CallbackQuery) -> None:
    await _show_orders(callback, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("menu:orders:page:"), ExchangeState.choosing_country)
async def menu_orders_page(callback: CallbackQuery) -> None:
    page = int(str(callback.data).rsplit(":", 1)[-1])
    await _show_orders(callback, edit=True, page=page)
    await callback.answer()


@router.callback_query(F.data == "menu:orders:noop", ExchangeState.choosing_country)
async def menu_orders_noop(callback: CallbackQuery) -> None:
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
    city_name = None
    db = await _get_db()
    async with db:
        city = await CityRepository(db).get_by_id(city_id)
    if city is not None:
        city_name = city.name
    await state.update_data(city_id=city_id, city_name=city_name)
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

    data = await state.get_data()
    min_amount = get_min_amount(str(data.get("method", "")), str(data["currency_sell"]))
    if min_amount is not None and amount < min_amount:
        logger.info(
            "Telegram exchange amount rejected below minimum: telegram_id=%s username=%s "
            "method=%s currency_sell=%s amount=%s min_amount=%s",
            getattr(message.from_user, "id", None),
            getattr(message.from_user, "username", None),
            data.get("method"),
            data.get("currency_sell"),
            amount,
            min_amount,
        )
        await state.set_state(ExchangeState.entering_amount)
        await message.answer(
            messages.amount_below_minimum(min_amount, translator=translate),
            reply_markup=amount_controls(translate),
        )
        return

    await state.update_data(amount_sell=amount)
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
    current_method = data.get("method")
    default_method = (
        current_method
        if isinstance(current_method, str) and current_method in methods
        else _select_default_method(methods)
    )
    await state.update_data(
        available_methods=methods,
        method=default_method,
        quote=_quote_to_state_payload(quote),
    )
    await state.set_state(ExchangeState.confirming)
    await _show_confirmation(message, state, edit=False)
    state_data = await state.get_data()
    prompt_message_id = state_data.get("amount_prompt_message_id")
    if prompt_message_id is not None:
        await _safe_delete_chat_message(message.bot, message.chat.id, int(prompt_message_id))
    await _safe_delete_message(message)


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
                country_value = (
                    ExchangeService()
                    .infer_country_from_pair(f"{data['currency_sell']}{data['currency_buy']}")
                    .value
                )
            city_id = data.get("city_id")
            if city_id is None and data["method"] == "cash":
                city_id = getattr(user, "city_id", None)
            created_order = await create_order_for_user(
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
                notify_user=False,
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

    availability = getattr(created_order, "manager_availability", None)
    await callback.message.answer(
        messages.order_created(
            created_order.publicNumber,
            translator=translate,
            managers_offline=getattr(availability, "status", None) == "offline",
        ),
        reply_markup=order_created_actions(translate),
    )
    await state.clear()
    await state.set_state(ExchangeState.choosing_country)
    await _safe_delete_message(callback.message)
    await callback.answer()


@router.callback_query(F.data == "fsm:back")
async def fsm_back(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state == ExchangeState.choosing_method.state:
        await _show_enter_amount_step(callback, state, edit=True)
    elif current_state == ExchangeState.entering_amount.state:
        await _show_currency_step(callback, state, edit=True)
    elif current_state in {
        ExchangeState.choosing_currency.state,
        ExchangeState.choosing_city.state,
    }:
        await _show_service_step(callback, state, edit=True)
    elif current_state == ExchangeState.choosing_service.state:
        await _show_start_welcome(callback, state, edit=True)
    elif current_state == ExchangeState.confirming.state:
        await _show_enter_amount_step(callback, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "fsm:cancel")
async def fsm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_start_welcome(callback, state, edit=True)
    await callback.answer()


def _quote_to_state_payload(quote) -> dict[str, object]:
    return {
        "currencySell": quote.currency_sell,
        "currencyBuy": quote.currency_buy,
        "amountSell": quote.amount_sell,
        "amountBuy": quote.amount_buy,
        "rate": quote.rate,
        "rateText": quote.rate_text,
    }
