"""Клавиатуры Telegram бота."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def home() -> ReplyKeyboardMarkup:
    """Главное меню пользователя."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="💱 Обмен"), KeyboardButton(text="📋 Мои заявки")]],
        resize_keyboard=True,
    )


def menu_operator() -> ReplyKeyboardMarkup:
    """Меню оператора."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Заявки"), KeyboardButton(text="✅ Подтвердить")],
            [KeyboardButton(text="❌ Отменить"), KeyboardButton(text="🏠 Главная")],
        ],
        resize_keyboard=True,
    )


def menu() -> ReplyKeyboardMarkup:
    """Меню обмена."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇷🇺 RUB → THB"), KeyboardButton(text="💎 USDT → THB")],
            [KeyboardButton(text="🏠 Главная")],
        ],
        resize_keyboard=True,
    )


def obtaining() -> InlineKeyboardMarkup:
    """Способ получения средств."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏧 Банкомат (QR)", callback_data="method:qr")],
            [InlineKeyboardButton(text="🏦 Перевод (RS)", callback_data="method:rs")],
            [InlineKeyboardButton(text="💵 Наличные", callback_data="method:cash")],
        ]
    )


def delivery_cash() -> InlineKeyboardMarkup:
    """Подтверждение доставки наличными."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить получение", callback_data="cash:confirm")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cash:cancel")],
        ]
    )


def confirm_order(order_id: int) -> InlineKeyboardMarkup:
    """Подтверждение заявки оператором."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"op:confirm:{order_id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"op:cancel:{order_id}")],
        ]
    )
