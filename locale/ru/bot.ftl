## Main menu
welcome = 👋 Привет, { $name }!
menu-exchange = 💱 Новый обмен
menu-orders = 📋 Мои заявки
menu-rate-header = 📊 Актуальные пары:
menu-rate-info =
    📊 Текущий курс:
    • 1 RUB = { $rub_rate } THB
    • 1 USDT = { $usdt_rate } THB
    🕐 Обновлено: { $updated_at }
home-title = 🏠 Главное меню
bot-disabled = ⚠️ Бот временно недоступен. Попробуйте позже.
bot-turned-on = ✅ Бот включён.
bot-turned-off = 🔴 Бот выключен.

## FSM — exchange flow
exchange-step = Шаг { $current } из { $total }
exchange-choose-currency = Выберите валюту для обмена:
exchange-choose-buy-currency = Выберите, что получить за { $currency }:
exchange-enter-amount = Введите сумму в { $currency }:
exchange-amount-invalid = ❌ Неверная сумма. Введите число больше 0.
exchange-choose-method = Как вы хотите получить { $currency }?
exchange-rate-unavailable = ⚠️ Курс временно недоступен. Попробуйте позже.
exchange-confirm-summary =
    📋 Подтверждение заявки — шаг { $current }/{ $total }

    Вы отправляете: { $amount } { $from_currency }
    Вы получаете:   { $result } { $to_currency }
    Способ:         { $method }

## Buttons
btn-confirm = ✅ Подтвердить
btn-cancel = ❌ Отменить
btn-back = ◀ Назад
btn-home = 🏠 Главное меню
btn-qr = 📱 QR-код
btn-transfer = 🏦 Перевод
btn-cash = 💵 Наличные
btn-wallet = 👛 Кошелек
btn-card = 💳 Карта
btn-cancel-order = ❌ Отменить
btn-confirm-cancel-order = ❌ Подтвердить отмену
btn-keep-order = ✅ Оставить
btn-take-order = ✅ В работу
btn-open-chat = 💬 Написать в чат
btn-write-manager = 💬 Написать менеджеру
btn-close-order = ✅ Закрыть заявку
btn-leave-review = ⭐ Оставить отзыв
btn-rub-thb = 🇷🇺 RUB → THB
btn-usdt-thb = 💎 USDT → THB
menu-open-site = 🚀 Открыть сайт

## Orders
orders-header = 📋 Ваши заявки:
orders-empty = 📭 У вас пока нет заявок.
orders-item = #{ $id }: { $amount_sell } { $currency_sell } → { $amount_buy } { $currency_buy }

## Order statuses
order-created =
    ✅ Заявка №{ $id } создана.

    ⏳ Мы получили ваш запрос и уже начали обработку.

    Пожалуйста, ожидайте подтверждения. Статус заявки будет обновлён автоматически.
order-confirmed =
    ✅ Заявка #{ $id } принята в работу.

    👨‍💼 Менеджер уже занимается вашим обменом.

    💬 Для связи используйте кнопку «Написать менеджеру».
order-cancelled = ❌ Заявка #{ $id } отменена.
order-completed =
    🎉 Заявка #{ $id } успешно завершена.

    Спасибо, что воспользовались нашим сервисом!

    ⭐ Если у вас есть пара минут, будем рады вашему отзыву. Это помогает нам становиться лучше.
