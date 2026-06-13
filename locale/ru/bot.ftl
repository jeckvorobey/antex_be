## Main menu
welcome =
    👋 { $name }, привет!

    Помогу быстро создать заявку на обмен без лишних шагов.
    Нажмите «Новый обмен», чтобы начать.

exchange-start-welcome =
    👋 Привет, { $name }!

    <b>AntEx</b> — это сервис, который помогает <u>быстро обменять деньги</u> и оплатить необходимые услуги без лишних усилий.

    📝 Чтобы оставить заявку, откройте приложение или выберите страну в списке ниже.

    ☝️ Мы будем сопровождать вас на каждом этапе.
exchange-choose-country = Выберите страну
exchange-choose-service =
    <b>💠 Выберите подходящую услугу</b>

    🚕 <i>Доставка наличных</i> — доставим денежные средства в удобное для вас место.
    🏧 <i>Наличные по QR</i> — получите наличные через банкомат.
    💳 <i>Перевод</i> — переведём средства на местный банковский счёт.
    🧰 <i>Оплата сервисов</i> — поможем оплатить необходимые услуги.
exchange-choose-city = Выберите город доставки наличных

menu-orders = 📋 Мои заявки
menu-new-site-leads = 🆕 Новые заявки
menu-rate-header = 🏦 Текущий курс:
home-title =
    🏠 Главное меню

    Выберите, что хотите сделать:
bot-disabled = ⚠️ Бот временно недоступен. Попробуйте позже.
bot-turned-on = ✅ Бот включён.
bot-turned-off = 🔴 Бот выключен.

## FSM — exchange flow
exchange-step = Шаг { $current }/{ $total }
exchange-choose-currency = Выберите валюту, которую хотите обменять.
exchange-choose-buy-currency = Выберите, что хотите получить за { $currency }:
exchange-enter-amount = <b>Введите сумму, которую хотите обменять в { $currency }:</b>
exchange-amount-invalid = Укажите сумму числом, больше нуля.
exchange-choose-method = Выберите способ получения { $currency }:
exchange-rate-unavailable = ⚠️ Курс временно недоступен. Попробуйте позже.
exchange-confirm-summary-top = 📋 Проверьте заявку — шаг { $current }/{ $total }
exchange-confirm-summary-bottom = Если всё верно, нажмите «Подтвердить».
exchange-summary-country = Страна
exchange-summary-city = Город
exchange-summary-rate = Курс
exchange-summary-sell = Отдаёте
exchange-summary-buy = Получаете
exchange-summary-method = Способ получения
manager-summary-user = Пользователь

## Buttons
btn-confirm = ✅ Подтвердить
btn-cancel = ❌ Отменить
btn-back = ◀ Назад
btn-service-cash-delivery = 🚕 Доставка наличных
btn-service-cash-atm = 🏧 Наличные по QR
btn-service-bank-account = 💳 Перевод на счёт в местном банке
btn-service-pay-services = 🧰 Оплата сервисов
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
menu-open-site = 🚀 Открыть приложение

## Orders
orders-header = 📋 Ваши заявки:
orders-empty = 📭 У вас пока нет заявок.
orders-item = #{ $id }: { $amount_sell } { $currency_sell } → { $amount_buy } { $currency_buy }

## Manager
manager-new-orders-header = 🆕 Новые заявки на обмен:
manager-new-orders-empty = 📭 Новых заявок на обмен нет.
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

    💬 Для связи используйте кнопку «Написать в чат».
order-completed =
    ✅ Заявка #{ $id } завершена.

    💱 Направление: { $direction }
    💸 Сумма: { $amount } { $currency }

    📍 { $city }

    🏁 Обмен успешно выполнен
order-completed-top =
    🎉 Заявка #{ $id } успешно завершена.
order-completed-bottom =
    Спасибо, что воспользовались нашим сервисом!

    ⭐ Если у вас есть пара минут, будем рады вашему отзыву. Это помогает нам становиться лучше.
order-cancelled = ❌ Заявка #{ $id } отменена.
manager-chat-open-text = Здравствуйте! Вы оставляли заявку #{ $id } на обмен { $amount } { $currency }. Готовы продолжить?
user-chat-open-text = Здравствуйте! По заявке #{ $id } на сумму { $amount } { $currency } подтверждаю готовность к обмену.
