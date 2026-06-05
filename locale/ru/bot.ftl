## Main menu
welcome =
    👋 { $name }, привет!

    Помогу быстро создать заявку на обмен без лишних шагов.
    Нажмите «Новый обмен», чтобы начать.
menu-exchange = 💱 Новый обмен
menu-orders = 📋 Мои заявки
menu-new-site-leads = 🆕 Новые заявки
menu-rate-header = 📊 Актуальные пары:
menu-rate-info =
    📊 Текущий курс:
    • 1 RUB = { $rub_rate } THB
    • 1 USDT = { $usdt_rate } THB
    🕐 Обновлено: { $updated_at }
home-title =
    🏠 Главное меню

    Выберите, что хотите сделать:
bot-disabled = ⚠️ Бот временно недоступен. Попробуйте позже.
bot-turned-on = ✅ Бот включён.
bot-turned-off = 🔴 Бот выключен.

## FSM — exchange flow
exchange-step = Шаг { $current } из { $total }
exchange-choose-currency = Выберите, что хотите отдать:
exchange-choose-buy-currency = Выберите, что хотите получить за { $currency }:
exchange-enter-amount = Введите сумму, которую хотите обменять в { $currency }:
exchange-amount-invalid = Укажите сумму числом, больше нуля.
exchange-choose-method = Выберите способ получения { $currency }:
exchange-rate-unavailable = ⚠️ Курс временно недоступен. Попробуйте позже.
exchange-confirm-summary =
    📋 Проверьте заявку — шаг { $current }/{ $total }

    Отдаёте: { $amount } { $from_currency }
    Получаете: { $result } { $to_currency }
    Способ получения: { $method }

    Если всё верно, нажмите «Подтвердить».

## Buttons
btn-confirm = ✅ Подтвердить
btn-cancel = ❌ Отменить
btn-back = ◀ Назад
btn-edit = ✏️ Редактировать
btn-home-red = 🔴 Вернуться в начало
btn-home = 🏠 Главное меню
btn-qr = 📱 По QR-коду
btn-transfer = 🏦 Перевод
btn-cash = 💵 Наличные
btn-wallet = 👛 Кошелёк
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

## Manager
manager-site-leads-header = 🆕 Новые заявки с сайта:
manager-site-leads-empty = 📭 Новых заявок с сайта нет.
manager-access-denied = Недостаточно прав.

## Order statuses
order-created =
    ✅ Заявка №{ $id } создана.

    ⏳ Мы получили ваш запрос и уже начали обработку.

    Пожалуйста, ожидайте подтверждения. Статус заявки будет обновлён автоматически.
order-creation-failed = Не удалось создать заявку. Попробуйте ещё раз через минуту.
order-creation-limit-reached = У вас уже слишком много активных заявок. Дождитесь обработки текущих или завершите их.
order-confirmed =
    ✅ Заявка #{ $id } принята в работу.

    👨‍💼 Менеджер уже занимается вашим обменом.

    💬 Для связи используйте кнопку «Написать менеджеру».
order-cancelled = ❌ Заявка #{ $id } отменена.
order-completed =
    🎉 Заявка #{ $id } успешно завершена.

    Спасибо, что воспользовались нашим сервисом!

    ⭐ Если у вас есть пара минут, будем рады вашему отзыву. Это помогает нам становиться лучше.
