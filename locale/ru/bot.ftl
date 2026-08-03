## Main menu
welcome =
    👋 { $name }, привет!

    Помогу быстро создать заявку на обмен без лишних шагов.
    Нажмите «Новый обмен», чтобы начать.

exchange-start-welcome =
    👋 Привет, { $name }!

    <b>AntEx</b> — это сервис, который помогает <u>быстро обменять деньги</u> и оплатить необходимые услуги без лишних усилий.

    📝 Чтобы оставить заявку, откройте приложение или выберите страну в списке ниже.

    Заявки принимаются круглосуточно.

    ☝️ Мы будем сопровождать вас на каждом этапе.
manager-working-hours = Менеджеры работают { $hours }.
exchange-choose-country = Выберите страну
exchange-choose-service =
    <b>💠 Выберите подходящую услугу</b>

    🚕 <u><i>Доставка наличных</i></u> — доставим денежные средства в удобное для вас место.
    🏧 <u><i>Наличные по QR</i></u> — получите наличные через банкомат.
    💳 <u><i>Перевод</i></u> — переведём средства на местный банковский счёт.
    🧰 <u><i>Оплата сервисов</i></u> — поможем оплатить необходимые услуги.
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
exchange-enter-amount-with-min = <b>Введите сумму, которую хотите обменять в { $currency }:</b>
    ⚠️ Минимальная сумма: <b>{ $minAmount } { $minCurrency }</b>
exchange-amount-invalid = Укажите сумму числом, больше нуля.
exchange-amount-below-minimum = Сумма должна быть не меньше { $minAmount }. Введите допустимую сумму для данного способа получения.
exchange-choose-method = Выберите способ получения { $currency }:
exchange-rate-unavailable = ⚠️ Курс временно недоступен. Попробуйте позже.
exchange-confirm-summary-top = 📋 Проверьте заявку — шаг { $current }/{ $total }
exchange-confirm-summary-bottom = Если всё верно, нажмите «Подтвердить».
exchange-off-hours-alert = Менеджер обработает заявку утром после начала рабочего дня.
exchange-off-hours-confirmation =
    ⚠️ Менеджеры сейчас не работают.

    Заявка будет обработана утром после начала рабочего дня. Создать её можно сейчас — режим работы не влияет на оформление.

    График: { $hours }.

    Если всё верно, нажмите «Да».
exchange-summary-country = Страна
exchange-summary-city = Город
exchange-summary-rate = Курс
exchange-summary-sell = Отдаёте
exchange-summary-buy = Получаете
exchange-summary-method = Способ получения
manager-summary-user = Пользователь

## Buttons
btn-confirm = ✅ Подтвердить
btn-yes = ✅ Да
btn-cancel = ❌ Отменить
btn-cancel-short = ❌ Отмена
btn-back = ◀ Назад
btn-service-cash-delivery = 🚕 Доставка наличных
btn-service-cash-atm = 🏧 Наличные по QR
btn-service-bank-account = 💳 Перевод
btn-service-pay-services = 🧰 Оплата сервисов
btn-edit = ✏️ Редактировать
btn-home-red = 🔴 Вернуться в начало
btn-home = 🏠 Главное меню
btn-qr = 📱 По QR-коду
btn-transfer = 🏦 Перевод
btn-cash = 💵 Наличные
btn-wallet = 👛 Кошелёк
btn-card = 💳 Карта
btn-cancel-order = ❌ Отменить заявку
btn-confirm-cancel-order = ❌ Подтвердить отмену
btn-keep-order = ✅ Оставить
btn-take-order = ✅ Взять в работу
btn-open-chat = 💬 Написать в чат
btn-write-manager = 💬 Написать менеджеру
btn-close-order = ✅ Закрыть заявку
btn-leave-review = ⭐ Оставить отзыв
menu-open-site = 🚀 Открыть приложение

## Orders
orders-header = 📋 Ваши заявки:
orders-empty = 📭 У вас пока нет заявок.
orders-item = #{ $id }: { $amount_sell } { $currency_sell } → { $amount_buy } { $currency_buy }
orders-item-rate-label = Курс
orders-item-method-label = Способ получения
orders-item-status-created = Новая
orders-item-status-processing = В работе
orders-item-status-completed = Завершена
orders-item-status-cancelled = Отменена
orders-item-method-cash = Доставка наличных
orders-item-method-qrcode = Наличные по QR
orders-item-method-bank-account = Перевод на счёт в местном банке
orders-item-method-pay-services = Оплата сервисов

## Manager
manager-new-orders-header = 🆕 Новые заявки на обмен:
manager-new-orders-empty = 📭 Новых заявок на обмен нет.
manager-access-denied = Недостаточно прав.

## Order statuses
order-created =
    ✅ Заявка №{ $id } создана.

    ⏳ Мы получили ваш запрос и уже начали обработку.

    Пожалуйста, ожидайте подтверждения. Статус заявки будет обновлён автоматически.
order-created-offline =
    ✅ Заявка №{ $id } создана.

    Заявка принята.

    <blockquote>Менеджер обработает заявку утром после начала рабочего дня.</blockquote>
order-creation-failed = Не удалось создать заявку. Попробуйте ещё раз через минуту.
order-created-notification-failed = Заявка #{ $id } создана, но подтверждение не удалось отправить. Откройте «Мои заявки», чтобы проверить статус.
order-creation-limit-reached = У вас уже слишком много активных заявок. Дождитесь обработки текущих или завершите их.
order-confirmed =
    ✅ Заявка #{ $id } принята в работу.

    👨‍💼 Менеджер уже занимается вашим обменом.

    💬 Для связи используйте кнопку «Написать в чат».
customer-manager-draft = Здравствуйте! Я по заявке #{ $id }. Готов продолжить обмен.
order-details-caption = Детали заявки
order-country-thailand = Таиланд
order-country-vietnam = Вьетнам
order-country-georgia = Грузия
order-country-internal = Внутренний обмен
order-handoff-rich =
    <footer>Статус заявки</footer>
    <h2>✅ Заявка #{ $id } принята в работу</h2>
    <p>Менеджер готов продолжить обмен.</p>
    <hr/>
    { $summary }
    <h3>Откройте диалог</h3>
    <p>Напишите менеджеру первым. После вашего сообщения он сможет ответить и согласовать детали обмена.</p>
order-handoff-html =
    <b>✅ Заявка #{ $id } принята в работу</b>

    Менеджер готов продолжить обмен.

    { $summary }

    <b>Откройте диалог</b>
    Напишите менеджеру первым. После вашего сообщения он сможет ответить и согласовать детали обмена.
order-reminder-rich =
    <footer>Напоминание по заявке</footer>
    <h2>🔔 Менеджер ожидает ваше сообщение по заявке #{ $id }</h2>
    <p>{ $direction }</p>
    <p>Напишите менеджеру первым, чтобы открыть диалог. После этого он сможет ответить и продолжить обмен.</p>
order-reminder-html =
    <b>🔔 Менеджер ожидает ваше сообщение по заявке #{ $id }</b>

    { $direction }

    Напишите менеджеру первым, чтобы открыть диалог. После этого он сможет ответить и продолжить обмен.
manager-order-card-footer = Статус заявки
manager-order-created-title = 🆕 Новая заявка #{ $id }
manager-order-created-lead = Ожидает решения менеджера.
manager-order-processing-title = ✅ Заявка #{ $id } принята в работу
manager-order-processing-lead = Клиенту отправлена просьба начать диалог. Ожидайте сообщения клиента.
manager-order-processing-failed-lead = Заявка в работе, но сообщение клиенту не доставлено. Отправьте напоминание после проверки настроек связи.
manager-order-completed-title = ✅ Заявка #{ $id } завершена
manager-order-completed-lead = Обмен успешно выполнен.
manager-order-cancelled-title = ❌ Заявка #{ $id } отменена
manager-order-cancelled-lead = Работа по заявке остановлена.
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

    Мы ценим обратную связь. За видео-отзыв (кружок) предоставляем <b>бонус 5$ к следующему обмену 💰</b>

    ⭐ Будем рады вашему отзыву. Это помогает нам становиться лучше.
order-cancelled = ❌ Заявка #{ $id } отменена.
manager-chat-open-text = Здравствуйте! Вы оставляли заявку #{ $id } на обмен { $amount } { $currency }. Готовы продолжить?
user-chat-open-text = Здравствуйте! По заявке #{ $id } на сумму { $amount } { $currency } подтверждаю готовность к обмену.
btn-write-manager = 💬 Написать менеджеру
btn-open-client-chat = 💬 Открыть чат с клиентом
btn-remind-client = 🔔 Напомнить клиенту
referral-bonus-credited =
    🎁 Вознаграждение по реферальной программе: +{ $amount } ATXG
    За успешно завершённую заявку #{ $order_id }.
referral-bonus-reversed =
    💸 Вознаграждение по реферальной программе списано: -{ $amount } ATXG
    Заявка #{ $order_id } отменена.
miniapp-aex-referral-reward = Реферальное начисление
miniapp-aex-referral-reward-with-order = Реферальное начисление по заявке { $order_number }
miniapp-aex-withdraw-hold = Зарезервировано
miniapp-aex-withdraw-hold-with-order = Зарезервировано по заявке { $order_number }
miniapp-aex-withdraw-debit = Списано
miniapp-aex-withdraw-debit-with-order = Списано по заявке { $order_number }
miniapp-aex-withdraw-release = Возврат
miniapp-aex-withdraw-release-with-order = Возврат по заявке { $order_number }
