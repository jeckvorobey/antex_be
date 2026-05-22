"""Inline клавиатуры Telegram бота."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import settings
from app.telegram.i18n import get_translator


def _resolve_translator(translator=None):
    return translator or get_translator()


def home(_, **kwargs) -> InlineKeyboardMarkup:
    """Главное меню пользователя: обмен + заявки."""
    del kwargs
    translate = _resolve_translator(_)
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=translate("menu-exchange"),
                callback_data="menu:exchange",
            ),
            InlineKeyboardButton(
                text=translate("menu-orders"),
                callback_data="menu:orders",
            ),
        ]
    ]

    if settings.frontend_webapp_url:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=translate("menu-open-site"),
                    web_app=WebAppInfo(url=settings.frontend_webapp_url),
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def choose_currency(_, currencies: list[str], **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг выбора валюты продажи."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=currency,
                    callback_data=f"exchange:currency:{currency}",
                )
                for currency in currencies
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                )
            ],
        ]
    )


def choose_buy_currency(_, currencies: list[str], **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг выбора валюты получения."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=currency,
                    callback_data=f"exchange:buy:{currency}",
                )
                for currency in currencies
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-back"),
                    callback_data="fsm:back",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                ),
            ],
        ]
    )


def obtaining(_, methods: list[str], **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг выбора способа получения."""
    del kwargs
    translate = _resolve_translator(_)
    method_labels = {
        "qr": translate("btn-qr"),
        "rs": translate("btn-transfer"),
        "cash": translate("btn-cash"),
        "wallet": translate("btn-wallet"),
        "card": translate("btn-card"),
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=method_labels.get(method, method.upper()),
                    callback_data=f"method:{method}",
                )
                for method in methods
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-back"),
                    callback_data="fsm:back",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                ),
            ],
        ]
    )


def confirm_exchange(_, **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг 4/4: confirm + cancel."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-confirm"),
                    callback_data="exchange:confirm",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                ),
            ]
        ]
    )


def confirm_order(_=None, *, order_id: int | None = None, **kwargs) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения заявки оператором."""
    del kwargs
    if order_id is None and isinstance(_, int):
        order_id = _
        _ = None
    if order_id is None:
        raise ValueError("order_id is required")

    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-open-chat"),
                    callback_data=f"op:open_chat:{order_id}",
                ),
            ]
        ]
    )


def manager_order_open_chat(
    _=None,
    *,
    order_id: int | None = None,
    **kwargs,
) -> InlineKeyboardMarkup:
    del kwargs
    return confirm_order(_, order_id=order_id)


def manager_order_close(_=None, *, order_id: int | None = None, **kwargs) -> InlineKeyboardMarkup:
    del kwargs
    if order_id is None and isinstance(_, int):
        order_id = _
        _ = None
    if order_id is None:
        raise ValueError("order_id is required")

    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-close-order"),
                    callback_data=f"op:close:{order_id}",
                )
            ]
        ]
    )


def review_link(_, url: str, **kwargs) -> InlineKeyboardMarkup:
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-leave-review"),
                    url=url,
                )
            ]
        ]
    )


def delivery_cash(_, **kwargs) -> InlineKeyboardMarkup:
    """Подтверждение получения наличных."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-confirm"),
                    callback_data="cash:confirm",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="cash:cancel",
                ),
            ]
        ]
    )
