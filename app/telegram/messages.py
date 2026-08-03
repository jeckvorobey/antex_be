# ruff: noqa: RUF002
"""Telegram bot message templates."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from typing import Any, cast

from app.enums.order import MethodGet, OrderStatus
from app.services.exchange import ExchangePairSnapshot
from app.telegram.i18n import get_translator
from app.telegram.message_templates import (
    EXCHANGE_CITY_TEMPLATE,
    EXCHANGE_CURRENCY_TEMPLATE,
    EXCHANGE_SERVICE_TEMPLATE,
    EXCHANGE_START_TEMPLATE,
    OFF_HOURS_BLOCK_TEMPLATE,
    WORKING_HOURS_BLOCK_TEMPLATE,
)
from app.telegram.order_cards import OrderMessageView, render_order_regular, render_order_rich

Translate = Callable[[str], str]
_CURRENCY_LABELS = {
    "RUB": "🇷🇺 RUB",
    "USDT": "₮ USDT",
    "THB": "🇹🇭 THB",
    "GEL": "🇬🇪 GEL",
    "VND": "🇻🇳 VND",
}
_CURRENCY_RATE_EMOJIS = {
    "USDT": "₮",
}
_CURRENCY_BUTTON_LABELS = {
    "USDT": "₮ USDT",
}
_ATXG_AMOUNT_QUANTIZER = Decimal("0.01")


def _resolve_translator(
    translator: Translate | None = None,
    locale: str | None = None,
) -> Translate:
    return translator or get_translator(locale)


def _strip_fluent_isolates(text: str) -> str:
    """Удаляет управляющие isolate-символы Fluent из contract-сообщений."""
    return text.replace("\u2068", "").replace("\u2069", "")


def format_currency_label(currency: str) -> str:
    return _CURRENCY_LABELS.get(currency.upper(), currency.upper())


def format_currency_button_label(currency: str) -> str:
    return _CURRENCY_BUTTON_LABELS.get(currency.upper(), format_currency_label(currency))


def _format_currency_emoji(currency: str) -> str:
    if currency.upper() in _CURRENCY_RATE_EMOJIS:
        return _CURRENCY_RATE_EMOJIS[currency.upper()]
    label = format_currency_label(currency)
    return label.split(maxsplit=1)[0]


def welcome(
    first_name: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("welcome", name=first_name)


def bot_disabled(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("bot-disabled")


def bot_turned_on(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("bot-turned-on")


def bot_turned_off(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("bot-turned-off")


def home_title(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("home-title")


def exchange_start_welcome(
    first_name: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
    business_hours_text: str | None = None,
    managers_offline: bool = False,
) -> str:
    """Собирает локализованное HTML-приветствие с режимом работы менеджеров."""
    translate = cast(Any, _resolve_translator(translator, locale))
    greeting = _strip_fluent_isolates(
        translate("exchange-start-greeting", name=escape(first_name))
    )
    working_hours_block = ""
    if business_hours_text is not None:
        working_hours_block = WORKING_HOURS_BLOCK_TEMPLATE.format(
            title=_strip_fluent_isolates(translate("manager-working-hours-title")),
            requests_anytime=_strip_fluent_isolates(translate("manager-requests-anytime")),
            managers_label=_strip_fluent_isolates(translate("manager-label")),
            hours=escape(business_hours_text),
        )

    off_hours_block = ""
    if managers_offline:
        off_hours_block = OFF_HOURS_BLOCK_TEMPLATE.format(
            title=_strip_fluent_isolates(translate("exchange-start-off-hours-title")),
            text=_strip_fluent_isolates(translate("exchange-start-off-hours-text")),
        )

    category = _strip_fluent_isolates(translate("exchange-start-category"))
    title = _strip_fluent_isolates(translate("exchange-start-title"))
    description = _strip_fluent_isolates(translate("exchange-start-description"))
    instruction_title = _strip_fluent_isolates(translate("exchange-start-instruction-title"))
    instruction = _strip_fluent_isolates(translate("exchange-start-instruction"))

    return EXCHANGE_START_TEMPLATE.format(
        greeting=greeting,
        category=category,
        title=title,
        description=description,
        instruction_title=instruction_title,
        instruction=instruction,
        working_hours_block=working_hours_block,
        off_hours_block=off_hours_block,
    )


def choose_country_prompt(
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-choose-country")


def choose_service_prompt(
    country: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Собирает Rich Message выбора услуги без технического счётчика шагов."""
    del country
    translate = cast(Any, _resolve_translator(translator, locale))
    return EXCHANGE_SERVICE_TEMPLATE.format(
        category=escape(_strip_fluent_isolates(translate("exchange-choose-service-category"))),
        title=escape(_strip_fluent_isolates(translate("exchange-choose-service-title"))),
        description=escape(_strip_fluent_isolates(translate("exchange-choose-service-description"))),
        options_title=escape(_strip_fluent_isolates(translate("exchange-choose-service-options-title"))),
        cash_delivery_title=escape(_strip_fluent_isolates(translate("exchange-service-cash-delivery-title"))),
        cash_delivery_description=escape(_strip_fluent_isolates(translate("exchange-service-cash-delivery-description"))),
        cash_atm_title=escape(_strip_fluent_isolates(translate("exchange-service-cash-atm-title"))),
        cash_atm_description=escape(_strip_fluent_isolates(translate("exchange-service-cash-atm-description"))),
        bank_account_title=escape(_strip_fluent_isolates(translate("exchange-service-bank-account-title"))),
        bank_account_description=escape(_strip_fluent_isolates(translate("exchange-service-bank-account-description"))),
        pay_services_title=escape(_strip_fluent_isolates(translate("exchange-service-pay-services-title"))),
        pay_services_description=escape(_strip_fluent_isolates(translate("exchange-service-pay-services-description"))),
    )


def choose_city_prompt(
    service: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Собирает Rich Message выбора города для доставки наличных."""
    del service
    translate = cast(Any, _resolve_translator(translator, locale))
    return EXCHANGE_CITY_TEMPLATE.format(
        category=escape(_strip_fluent_isolates(translate("exchange-choose-city-category"))),
        title=escape(_strip_fluent_isolates(translate("exchange-choose-city-title"))),
        description=escape(_strip_fluent_isolates(translate("exchange-choose-city-description"))),
        options_title=escape(_strip_fluent_isolates(translate("exchange-choose-city-options-title"))),
        options_hint=escape(_strip_fluent_isolates(translate("exchange-choose-city-options-hint"))),
    )


def exchange_step(
    current: int,
    total: int,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-step", current=current, total=total)


def _country_label(country: str | None, translate: Translate) -> str:
    """Возвращает локализованное название страны из состояния сценария."""
    if country is None:
        return ""
    translation_key = {
        "thailand": "order-country-thailand",
        "vietnam": "order-country-vietnam",
        "georgia": "order-country-georgia",
        "internal": "order-country-internal",
    }.get(country.lower())
    return (
        _strip_fluent_isolates(translate(translation_key))
        if translation_key is not None
        else country
    )


def choose_currency_prompt(
    pairs: list[ExchangePairSnapshot],
    *,
    country: str | None = None,
    service: str | None = None,
    city: str | None = None,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Собирает Rich Message выбора валюты с контекстом заявки и курсами."""
    translate = cast(Any, _resolve_translator(translator, locale))
    if not pairs:
        return translate("exchange-rate-unavailable")

    selection = [
        (
            _strip_fluent_isolates(translate("exchange-choose-currency-summary-country")),
            _country_label(country, translate),
        ),
        (
            _strip_fluent_isolates(translate("exchange-choose-currency-summary-service")),
            _strip_fluent_isolates(service) if service else "",
        ),
    ]
    if city:
        selection.append(
            (
                _strip_fluent_isolates(translate("exchange-choose-currency-summary-city")),
                _strip_fluent_isolates(city),
            )
        )
    selection_rows = "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in selection
        if value
    )
    rate_items = "\n".join(
        (
            "<li>"
            f"<b>{_format_currency_emoji(pair.currency_sell)} {escape(pair.currency_sell)} "
            f"→ {_format_currency_emoji(pair.currency_buy)} {escape(pair.currency_buy)}</b><br/>"
            f"1 {escape(pair.currency_sell)} "
            f"{escape(_strip_fluent_isolates(translate('exchange-choose-currency-rate-from')))} "
            f"<b>{escape(pair.rate_display)} {escape(pair.currency_buy)}</b>"
            "</li>"
        )
        for pair in pairs
    )
    return EXCHANGE_CURRENCY_TEMPLATE.format(
        category=escape(_strip_fluent_isolates(translate("exchange-choose-currency-category"))),
        title=escape(_strip_fluent_isolates(translate("exchange-choose-currency-title"))),
        description=escape(_strip_fluent_isolates(translate("exchange-choose-currency-description"))),
        selection_title=escape(
            _strip_fluent_isolates(translate("exchange-choose-currency-selection-title"))
        ),
        selection_rows=selection_rows,
        rates_title=escape(_strip_fluent_isolates(translate("exchange-choose-currency-rates-title"))),
        rate_items=rate_items,
        options_hint=escape(_strip_fluent_isolates(translate("exchange-choose-currency-options-hint"))),
    )


def enter_amount_prompt(
    currency: str,
    min_amount: int | None = None,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = _resolve_translator(translator, locale)
    if min_amount is None:
        return translate(
            "exchange-enter-amount",
            currency=format_currency_label(currency),
        )

    text = _strip_fluent_isolates(
        translate(
            "exchange-enter-amount-with-min",
            currency=format_currency_label(currency),
            minAmount=str(min_amount),
            minCurrency=currency.upper(),
        )
    )
    return text.replace("\n⚠️", "\n\n⚠️", 1)


def invalid_amount(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("exchange-amount-invalid")


def amount_below_minimum(
    min_amount: int,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _strip_fluent_isolates(
        _resolve_translator(translator, locale)(
            "exchange-amount-below-minimum",
            minAmount=str(min_amount),
        )
    )


def choose_method_prompt(
    currency: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-choose-method", currency=currency)


def exchange_rate_unavailable(
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("exchange-rate-unavailable")


def _format_number(value: int | float) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    text = f"{value:,.2f}"
    return text.rstrip("0").rstrip(".")


def _format_aex_amount(value: Decimal | int | float | str) -> str:
    amount = Decimal(str(value)).quantize(_ATXG_AMOUNT_QUANTIZER)
    return f"{amount:.2f}"


def exchange_summary_middle(
    *,
    country: str,
    rate: str,
    amount: int | float,
    from_currency: str,
    result: int | float,
    to_currency: str,
    method: str,
    city: str | None = None,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    lines = [f"🌍 {translate('exchange-summary-country')}: {country}"]
    if city:
        lines.append(f"🏙️ {translate('exchange-summary-city')}: {city}")
    lines.append(f"📈 {translate('exchange-summary-rate')}: {rate}")
    sell_label = format_currency_label(from_currency)
    buy_label = format_currency_label(to_currency)
    lines.append(f"💸 {translate('exchange-summary-sell')}: {_format_number(amount)} {sell_label}")
    lines.append(f"💰 {translate('exchange-summary-buy')}: {_format_number(result)} {buy_label}")
    lines.append(f"🧾 {translate('exchange-summary-method')}: {method}")
    return "\n".join(lines)


def exchange_confirm_summary(
    *,
    country: str,
    rate: str,
    amount: int,
    from_currency: str,
    result: int | float,
    to_currency: str,
    method: str,
    city: str | None = None,
    current: int = 4,
    total: int = 4,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    summary = exchange_summary_middle(
        country=country,
        rate=rate,
        amount=amount,
        from_currency=from_currency,
        result=result,
        to_currency=to_currency,
        method=method,
        city=city,
        translator=translate,
    )
    return "\n".join(
        [
            translate("exchange-confirm-summary-top", current=current, total=total),
            "",
            summary,
            "",
            translate("exchange-confirm-summary-bottom"),
        ]
    )


def exchange_off_hours_confirmation(
    business_hours_text: str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Предупреждение перед созданием заявки вне режима работы менеджеров."""
    return _resolve_translator(translator, locale)(
        "exchange-off-hours-confirmation",
        hours=business_hours_text,
    )


def exchange_off_hours_alert(
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Короткий Telegram alert для off-hours подтверждения."""
    return _resolve_translator(translator, locale)("exchange-off-hours-alert")


def manager_order_summary(
    *,
    country: str,
    rate: str,
    amount_sell: int | float,
    from_currency: str,
    amount_buy: int | float,
    to_currency: str,
    method: str,
    username: str,
    city: str | None = None,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    summary = exchange_summary_middle(
        country=country,
        rate=rate,
        amount=amount_sell,
        from_currency=from_currency,
        result=amount_buy,
        to_currency=to_currency,
        method=method,
        city=city,
        translator=translate,
    )
    return "\n".join([summary, "", f"👤 {translate('manager-summary-user')}: {username}"])


def manager_chat_open_text(
    *,
    order_id: int | str,
    amount_sell: int | float,
    currency_sell: str,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    return translate(
        "manager-chat-open-text",
        id=order_id,
        amount=_format_number(amount_sell),
        currency=currency_sell,
    )


def referral_bonus_credited(
    *,
    amount: Decimal | int | float | str,
    order_id: int | str,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Текст уведомления рефереру о начислении ATXG."""
    translate = cast(Any, _resolve_translator(translator, locale))
    return translate(
        "referral-bonus-credited",
        amount=_format_aex_amount(amount),
        order_id=order_id,
    )


def referral_bonus_reversed(
    *,
    amount: Decimal | int | float | str,
    order_id: int | str,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Текст уведомления о списании ATXG при отмене заявки."""
    translate = cast(Any, _resolve_translator(translator, locale))
    return translate(
        "referral-bonus-reversed",
        amount=_format_aex_amount(amount),
        order_id=order_id,
    )


def user_chat_open_text(
    *,
    order_id: int | str,
    amount_sell: int | float,
    currency_sell: str,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    return translate(
        "user-chat-open-text",
        id=order_id,
        amount=_format_number(amount_sell),
        currency=currency_sell,
    )


def customer_manager_draft(
    order_id: int | str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Подготовленный клиенту текст для первого сообщения менеджеру."""
    return _strip_fluent_isolates(
        _resolve_translator(translator, locale)("customer-manager-draft", id=order_id)
    )


def order_handoff_rich(
    view: OrderMessageView,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Rich HTML-инструкция клиенту после принятия заявки."""
    translate = _resolve_translator(translator, locale)
    current_locale = locale or "ru"
    return _strip_fluent_isolates(
        translate(
            "order-handoff-rich",
            id=escape(view.public_number),
            summary=render_order_rich(view, locale=current_locale),
        )
    )


def order_handoff_html(
    view: OrderMessageView,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Обычный HTML fallback для инструкции клиенту."""
    translate = _resolve_translator(translator, locale)
    current_locale = locale or "ru"
    return _strip_fluent_isolates(
        translate(
            "order-handoff-html",
            id=escape(view.public_number),
            summary=render_order_regular(view, locale=current_locale),
        )
    )


def order_reminder_rich(
    view: OrderMessageView,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Короткое Rich-напоминание клиенту без ложной срочности."""
    translate = _resolve_translator(translator, locale)
    return _strip_fluent_isolates(
        translate(
            "order-reminder-rich",
            id=escape(view.public_number),
            direction=escape(view.direction or ""),
        )
    )


def order_reminder_html(
    view: OrderMessageView,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    """Обычный HTML fallback напоминания."""
    translate = _resolve_translator(translator, locale)
    return _strip_fluent_isolates(
        translate(
            "order-reminder-html",
            id=escape(view.public_number),
            direction=escape(view.direction or ""),
        )
    )


def _manager_order_card_copy(
    view: OrderMessageView,
    *,
    status: OrderStatus,
    customer_notified: bool,
    locale: str,
) -> tuple[str, str]:
    translate = _resolve_translator(locale=locale)
    status_key = {
        OrderStatus.CREATED: "created",
        OrderStatus.PROCESSING: "processing",
        OrderStatus.COMPLETED: "completed",
        OrderStatus.CANCELLED: "cancelled",
    }[OrderStatus(int(status))]
    title = _strip_fluent_isolates(
        translate(f"manager-order-{status_key}-title", id=escape(view.public_number))
    )
    lead_key = f"manager-order-{status_key}-lead"
    if status == OrderStatus.PROCESSING and not customer_notified:
        lead_key = "manager-order-processing-failed-lead"
    return title, translate(lead_key)


def manager_order_card_rich(
    view: OrderMessageView,
    *,
    status: OrderStatus,
    customer_notified: bool = True,
    locale: str = "ru",
) -> str:
    """Собрать единую Rich-карточку заявки для менеджера."""
    translate = _resolve_translator(locale=locale)
    title, lead = _manager_order_card_copy(
        view,
        status=status,
        customer_notified=customer_notified,
        locale=locale,
    )
    summary = render_order_rich(view, locale=locale, include_customer=True)
    return (
        f"<footer>{escape(translate('manager-order-card-footer'))}</footer>"
        f"<h2>{title}</h2>"
        f"<p>{escape(lead)}</p>"
        f"<hr/>{summary}"
    )


def manager_order_card_html(
    view: OrderMessageView,
    *,
    status: OrderStatus,
    customer_notified: bool = True,
    locale: str = "ru",
) -> str:
    """Собрать regular HTML fallback manager-карточки."""
    title, lead = _manager_order_card_copy(
        view,
        status=status,
        customer_notified=customer_notified,
        locale=locale,
    )
    summary = render_order_regular(view, locale=locale, include_customer=True)
    return f"<b>{title}</b>\n\n{escape(lead)}\n\n{summary}"


def exchange_rate(sell_rate: float, buy_rate: float) -> str:
    return f"{sell_rate:.2f} / {buy_rate:.2f}"


def exchange_pair_rates(
    pairs: list[ExchangePairSnapshot],
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    if not pairs:
        return translate("exchange-rate-unavailable")

    def _format_pair(pair: ExchangePairSnapshot) -> str:
        return (
            f"{_format_currency_emoji(pair.currency_sell)} 1 {pair.currency_sell} "
            f"от {pair.rate_display} {pair.currency_buy} "
            f"{_format_currency_emoji(pair.currency_buy)}"
        )

    return "\n".join(_format_pair(pair) for pair in pairs)


def order_created(
    order_id: int | str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
    managers_offline: bool = False,
) -> str:
    translate = _resolve_translator(translator, locale)
    if managers_offline:
        return translate("order-created-offline", id=order_id)
    return translate("order-created", id=order_id)


def order_creation_failed(
    *,
    code: str | None = None,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    if code == "ORDER_ALREADY_EXISTS":
        return translate("order-creation-limit-reached")
    return translate("order-creation-failed")


def order_confirmed(
    order_id: int | str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("order-confirmed", id=order_id)


def order_completed(
    order_id: int | str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("order-completed-top", id=order_id)


def order_completed_bottom(
    *, translator: Translate | None = None, locale: str | None = None
) -> str:
    return _resolve_translator(translator, locale)("order-completed-bottom")


def order_cancelled(
    order_id: int | str,
    *,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    return _resolve_translator(translator, locale)("order-cancelled", id=order_id)


def orders_empty(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("orders-empty")


def orders_header(*, translator: Translate | None = None, locale: str | None = None) -> str:
    return _resolve_translator(translator, locale)("orders-header")


def orders_item(
    *,
    order_id: int | str,
    status: int | None,
    amount_sell: int | float,
    currency_sell: str,
    amount_buy: int | float,
    currency_buy: str,
    rate: int | float | str | None,
    method: str | None,
    created_at: datetime | None,
    updated_at: datetime | None,
    end_time: datetime | None,
    translator: Translate | None = None,
    locale: str | None = None,
) -> str:
    translate = cast(Any, _resolve_translator(translator, locale))
    return "\n".join(
        [
            f"#{order_id}: {_format_order_status_label(status, translate=translate)}",
            (
                f"{_format_order_amount(amount_sell)} {format_currency_label(currency_sell)}"
                f" → {_format_order_amount(amount_buy)} {format_currency_label(currency_buy)}"
            ),
            f"{translate('orders-item-rate-label')}: {_format_order_rate(rate)}",
            (
                f"{translate('orders-item-method-label')}: "
                f"{_format_order_method(method, translate=translate)}"
            ),
            _format_order_list_date(
                created_at=created_at,
                updated_at=updated_at,
                end_time=end_time,
            ),
        ]
    )


def _format_order_status_label(status: int | None, *, translate) -> str:
    if status == int(OrderStatus.CREATED):
        return translate("orders-item-status-created")
    if status == int(OrderStatus.PROCESSING):
        return translate("orders-item-status-processing")
    if status == int(OrderStatus.COMPLETED):
        return translate("orders-item-status-completed")
    if status == int(OrderStatus.CANCELLED):
        return translate("orders-item-status-cancelled")
    return "—"


def _format_order_rate(rate: int | float | str | None) -> str:
    if rate is None:
        return "—"
    return str(rate)


def _format_order_amount(amount: int | float) -> str:
    return f"{amount:,}"


def _format_order_method(method: str | None, *, translate) -> str:
    if method == MethodGet.CASH.value:
        return translate("orders-item-method-cash")
    if method == MethodGet.QRCODE.value:
        return translate("orders-item-method-qrcode")
    if method == MethodGet.BANK_ACCOUNT.value:
        return translate("orders-item-method-bank-account")
    if method == MethodGet.PAY_SERVICES.value:
        return translate("orders-item-method-pay-services")
    return method or "—"


def _format_order_list_date(
    *,
    created_at: datetime | None,
    updated_at: datetime | None,
    end_time: datetime | None,
) -> str:
    stamp = created_at or updated_at or end_time
    if stamp is None:
        return "—"
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")


def new_order_operator(
    order_id: int,
    user_id: int,
    amount_sell: int,
    currency_sell: str,
    amount_buy: int,
    currency_buy: str,
    method: str,
) -> str:
    return (
        f"🆕 <b>Новая заявка #{order_id}</b>\n\n"
        f"👤 Пользователь: <code>{user_id}</code>\n"
        f"💸 Отдаёт: <b>{amount_sell:,} {currency_sell}</b>\n"
        f"💰 Получает: <b>{amount_buy:,} {currency_buy}</b>\n"
        f"📦 Способ: <b>{method}</b>"
    )