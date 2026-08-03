"""Inline клавиатуры Telegram бота."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import settings
from app.enums.country import Country
from app.telegram.i18n import get_translator
from app.telegram.messages import format_currency_button_label


def _resolve_translator(translator=None):
    return translator or get_translator()


def _chat_url_with_draft(chat_url: str, message_text: str | None = None) -> str:
    if not message_text:
        return chat_url

    parsed = urlparse(chat_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc == "t.me":
        path = parsed.path.strip("/")
        if path:
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query["text"] = message_text
            return urlunparse(parsed._replace(query=urlencode(query)))

    if parsed.scheme == "tg" and parsed.netloc == "resolve":
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if query.get("domain"):
            query["text"] = message_text
            return urlunparse(parsed._replace(query=urlencode(query)))

    return chat_url


def _chat_button(
    translate,
    chat_url: str,
    *,
    label_key: str,
    message_text: str | None = None,
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=translate(label_key),
        url=_chat_url_with_draft(chat_url, message_text),
    )


def _city_label(city: object) -> str:
    name = getattr(city, "name", str(city))
    country = getattr(city, "country", None)
    if isinstance(country, Country):
        flag = country.flag
    else:
        try:
            flag = Country(str(country)).flag if country is not None else ""
        except ValueError:
            flag = ""
    return f"{flag} {name}".strip()


COUNTRY_CITY_BUTTONS = {
    "thailand": [("pattya", "Паттайя"), ("phuket", "Пхукет")],
    "vietnam": [("danang", "Дананг"), ("nhatrang", "Нячанг"), ("phuquoc", "Фукуок")],
    "georgia": [("batumi", "Батуми"), ("tbilisi", "Тбилиси")],
}


def choose_country(_, **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг выбора страны."""
    del kwargs
    translate = _resolve_translator(_)
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=translate("country-thailand"), callback_data="exchange:country:thailand"
            ),
            InlineKeyboardButton(
                text=translate("country-vietnam"), callback_data="exchange:country:vietnam"
            ),
            InlineKeyboardButton(
                text=translate("country-georgia"), callback_data="exchange:country:georgia"
            ),
        ],
        [
            InlineKeyboardButton(
                text=translate("menu-orders"),
                callback_data="menu:orders",
                style="primary",
            )
        ],
    ]

    if settings.frontend_webapp_url:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=translate("menu-open-site"),
                    web_app=WebAppInfo(url=settings.frontend_webapp_url),
                    style="success",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def start_channel_choice(_, **kwargs) -> InlineKeyboardMarkup:
    """Равноправный выбор канала создания пользовательской заявки."""
    del kwargs
    translate = _resolve_translator(_)
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=translate("btn-start-telegram"),
                callback_data="exchange:start",
                style="primary",
            )
        ]
    ]
    if settings.frontend_webapp_url:
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=translate("btn-start-miniapp"),
                    web_app=WebAppInfo(url=settings.frontend_webapp_url),
                    style="success",
                )
            ]
        )
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate("menu-orders"),
                callback_data="menu:orders",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def choose_city(_, cities: list[object], **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг выбора города."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_city_label(city),
                    callback_data=f"exchange:city:{city.id}",
                )
                for city in cities
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-back"),
                    callback_data="fsm:back",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                    style="danger",
                ),
            ],
        ]
    )


def back_to_main_menu(_, **kwargs) -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-home"),
                    callback_data="fsm:cancel",
                    style="primary",
                )
            ]
        ]
    )


def orders_pagination(
    _, *, page: int, total: int, page_size: int = 10, **kwargs
) -> InlineKeyboardMarkup:
    """Order history keyboard with pagination controls."""
    del kwargs
    translate = _resolve_translator(_)
    inline_keyboard: list[list[InlineKeyboardButton]] = []

    if total > page_size:
        pages = max(1, (total + page_size - 1) // page_size)
        current_page = min(max(1, page), pages)
        row: list[InlineKeyboardButton] = []
        if current_page > 1:
            row.append(
                InlineKeyboardButton(
                    text="◀",
                    callback_data=f"menu:orders:page:{current_page - 1}",
                )
            )
        row.append(
            InlineKeyboardButton(
                text=f"{current_page}/{pages}",
                callback_data="menu:orders:noop",
            )
        )
        if current_page < pages:
            row.append(
                InlineKeyboardButton(
                    text="▶",
                    callback_data=f"menu:orders:page:{current_page + 1}",
                )
            )
        inline_keyboard.append(row)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate("btn-home"),
                callback_data="fsm:cancel",
                style="primary",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def order_created_actions(_, **kwargs) -> InlineKeyboardMarkup:
    """Кнопки после создания заявки."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("menu-orders"),
                    callback_data="menu:orders",
                    style="primary",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-home"),
                    callback_data="fsm:cancel",
                    style="primary",
                )
            ],
        ]
    )


def choose_service(_, **kwargs) -> InlineKeyboardMarkup:
    """FSM шаг выбора услуги."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-service-cash-delivery"),
                    callback_data="exchange:service:cash_delivery",
                ),
                InlineKeyboardButton(
                    text=translate("btn-service-cash-atm"),
                    callback_data="exchange:service:cash_atm",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-service-bank-account"),
                    callback_data="exchange:service:bank_account",
                ),
                InlineKeyboardButton(
                    text=translate("btn-service-pay-services"),
                    callback_data="exchange:service:pay_services",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-back"),
                    callback_data="fsm:back",
                )
            ],
        ]
    )


def manager_home(_, **kwargs) -> InlineKeyboardMarkup:
    """Главное меню менеджера: новые заявки + сайт."""
    del kwargs
    translate = _resolve_translator(_)
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=translate("menu-new-site-leads"),
                callback_data="manager:new_orders",
            )
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


def _truncate_button_text(text: str, *, limit: int = 48) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def manager_new_orders_list(_, orders: list[object], **kwargs) -> InlineKeyboardMarkup:
    """Инлайн-лист новых заявок на обмен для менеджера."""
    del kwargs
    translate = _resolve_translator(_)
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=_truncate_button_text(
                    f"🆕 #{getattr(order, 'publicNumber', order.id)} "
                    f"{order.currencySell} → {order.currencyBuy}"
                ),
                callback_data=f"manager:order:{order.id}",
            )
        ]
        for order in orders
    ]
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=translate("menu-new-site-leads"),
                callback_data="manager:new_orders",
            )
        ]
    )

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
                    text=format_currency_button_label(currency),
                    callback_data=f"exchange:currency:{currency}",
                )
                for currency in currencies
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-back"),
                    callback_data="fsm:back",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                    style="danger",
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


def amount_controls(_, **kwargs) -> InlineKeyboardMarkup:
    """FSM управление на шаге ввода суммы."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-back"),
                    callback_data="fsm:back",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel"),
                    callback_data="fsm:cancel",
                    style="danger",
                ),
            ]
        ]
    )


def confirm_exchange(_, **kwargs) -> InlineKeyboardMarkup:
    """Финальный шаг: подтвердить, отредактировать или вернуться в начало."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-confirm"),
                    callback_data="exchange:confirm",
                    style="success",
                ),
                InlineKeyboardButton(
                    text=translate("btn-edit"),
                    callback_data="fsm:back",
                    style="primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-home-red"),
                    callback_data="fsm:cancel",
                    style="danger",
                )
            ],
        ]
    )


def confirm_off_hours_exchange(_, **kwargs) -> InlineKeyboardMarkup:
    """Подтверждение создания заявки, когда менеджеры сейчас не работают."""
    del kwargs
    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("btn-yes"),
                    callback_data="exchange:confirm_offline",
                    style="success",
                ),
                InlineKeyboardButton(
                    text=translate("btn-cancel-short"),
                    callback_data="fsm:cancel",
                    style="danger",
                ),
            ]
        ]
    )


def confirm_order(
    _=None,
    *,
    order_id: int | None = None,
    chat_url: str | None = None,
    message_text: str | None = None,
    **kwargs,
) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения заявки оператором."""
    del kwargs, chat_url, message_text
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
                    text=translate("btn-cancel-order"),
                    callback_data=f"op:cancel:{order_id}",
                    style="danger",
                ),
                InlineKeyboardButton(
                    text=translate("btn-take-order"),
                    callback_data=f"op:take:{order_id}",
                    style="success",
                ),
            ],
        ]
    )


def manager_order_open_chat(
    _=None,
    *,
    order_id: int | None = None,
    chat_url: str | None = None,
    message_text: str | None = None,
    **kwargs,
) -> InlineKeyboardMarkup:
    del kwargs
    return confirm_order(_, order_id=order_id, chat_url=chat_url, message_text=message_text)


def manager_order_close(
    _=None,
    *,
    order_id: int | None = None,
    chat_url: str | None = None,
    message_text: str | None = None,
    **kwargs,
) -> InlineKeyboardMarkup:
    del kwargs
    if order_id is None and isinstance(_, int):
        order_id = _
        _ = None
    if order_id is None:
        raise ValueError("order_id is required")
    if not chat_url:
        raise ValueError("chat_url is required")

    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _chat_button(
                    translate,
                    chat_url,
                    label_key="btn-open-client-chat",
                    message_text=message_text,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-remind-client"),
                    callback_data=f"op:remind:{order_id}",
                    style="primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-cancel-order"),
                    callback_data=f"op:cancel:{order_id}",
                    style="danger",
                ),
                InlineKeyboardButton(
                    text=translate("btn-close-order"),
                    callback_data=f"op:close:{order_id}",
                    style="success",
                ),
            ],
        ]
    )


def manager_order_cancel_confirm(
    _=None,
    *,
    order_id: int | None = None,
    **kwargs,
) -> InlineKeyboardMarkup:
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
                    text=translate("btn-confirm-cancel-order"),
                    callback_data=f"op:cancel_confirm:{order_id}",
                    style="danger",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-keep-order"),
                    callback_data=f"op:cancel_keep:{order_id}",
                    style="primary",
                ),
            ],
        ]
    )


def manager_order_chat_only(
    _=None,
    *,
    chat_url: str | None = None,
    message_text: str | None = None,
    **kwargs,
) -> InlineKeyboardMarkup:
    del kwargs
    if not chat_url:
        raise ValueError("chat_url is required")

    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _chat_button(
                    translate,
                    chat_url,
                    label_key="btn-open-client-chat",
                    message_text=message_text,
                ),
            ]
        ]
    )


def user_order_write_manager(
    _=None,
    *,
    chat_url: str | None = None,
    message_text: str | None = None,
    **kwargs,
) -> InlineKeyboardMarkup:
    del kwargs
    if not chat_url:
        raise ValueError("chat_url is required")

    translate = _resolve_translator(_)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _chat_button(
                    translate,
                    chat_url,
                    label_key="btn-write-manager",
                    message_text=message_text,
                ),
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
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("btn-home"),
                    callback_data="fsm:cancel",
                    style="primary",
                )
            ],
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
