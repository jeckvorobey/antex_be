"""Шаблоны сообщений Telegram бота."""

from __future__ import annotations


def welcome(first_name: str) -> str:
    return (
        f"👋 Привет, <b>{first_name}</b>!\n\n"
        "Добро пожаловать в <b>AntEx</b> — обменник валют в Таиланде.\n\n"
        "💱 Обмениваю: RUB / USDT → THB\n"
        "⚡️ Быстро, удобно, выгодно."
    )


def bot_disabled() -> str:
    return "⚠️ Бот временно недоступен. Попробуйте позже."


def exchange_rate(rubthb: float, allowance: float) -> str:
    return (
        f"📊 <b>Текущий курс</b>\n\n"
        f"🇷🇺 1 RUB = <b>{rubthb:.4f} THB</b>\n"
        f"📈 Надбавка: {allowance * 100:.1f}%"
    )


def order_created(order_id: int, amount_sell: int, currency_sell: str, amount_buy: int, currency_buy: str) -> str:
    return (
        f"✅ <b>Заявка #{order_id} создана</b>\n\n"
        f"Отдаёте: <b>{amount_sell:,} {currency_sell}</b>\n"
        f"Получаете: <b>{amount_buy:,} {currency_buy}</b>\n\n"
        "Ожидайте подтверждения оператора."
    )


def order_confirmed(order_id: int) -> str:
    return f"✅ Заявка #{order_id} подтверждена. Ожидайте перевода."


def order_completed(order_id: int) -> str:
    return f"🎉 Заявка #{order_id} завершена. Спасибо за обмен!"


def order_cancelled(order_id: int) -> str:
    return f"❌ Заявка #{order_id} отменена."


def enter_amount(currency: str) -> str:
    return f"Введите сумму в <b>{currency}</b> для обмена:"


def invalid_amount() -> str:
    return "❌ Неверная сумма. Введите целое число больше 0."


def new_order_operator(order_id: int, user_id: int, amount_sell: int, currency_sell: str,
                       amount_buy: int, currency_buy: str, method: str) -> str:
    return (
        f"🆕 <b>Новая заявка #{order_id}</b>\n\n"
        f"👤 Пользователь: <code>{user_id}</code>\n"
        f"💸 Отдаёт: <b>{amount_sell:,} {currency_sell}</b>\n"
        f"💰 Получает: <b>{amount_buy:,} {currency_buy}</b>\n"
        f"📦 Способ: <b>{method}</b>"
    )
