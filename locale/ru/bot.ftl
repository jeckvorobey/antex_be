## Main menu
welcome =
    👋 { $name }, привет!

    Помогу быстро создать заявку на обмен без лишних шагов.
    Нажмите «Новый обмен», чтобы начать.
start-customer-eyebrow = AntEx · Обмен валюты
start-customer-title = Здравствуйте, { $name }
start-customer-lead = Создайте заявку в привычном Telegram или откройте приложение с расширенным интерфейсом.
start-customer-hours = Заявки принимаем круглосуточно. Менеджеры работают { $hours }.
start-customer-action = Выберите удобный способ создания заявки.
start-manager-eyebrow = AntEx · Рабочее место
start-manager-title = Здравствуйте, { $name }
start-manager-lead = Здесь собраны новые заявки и быстрый переход в приложение.
start-manager-action = Откройте новые заявки, чтобы начать работу.

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
exchange-step = Новая заявка
exchange-stage-country = Новая заявка · Страна
exchange-stage-service = Новая заявка · Способ получения
exchange-stage-city = Новая заявка · Город
exchange-stage-currency = Новая заявка · Валюта
exchange-stage-amount = Новая заявка · Сумма
exchange-stage-summary = Новая заявка · Проверка
exchange-choose-currency = Выберите валюту, которую хотите обменять.
exchange-choose-buy-currency = Выберите, что хотите получить за { $currency }:
exchange-enter-amount = <b>Введите сумму, которую хотите обменять в { $currency }:</b>
exchange-enter-amount-with-min = <b>Введите сумму, которую хотите обменять в { $currency }:</b>
    ⚠️ Минимальная сумма: <b>{ $minAmount } { $minCurrency }</b>
exchange-amount-invalid = Укажите сумму числом, больше нуля.
exchange-amount-below-minimum = Сумма должна быть не меньше { $minAmount }. Введите допустимую сумму для данного способа получения.
exchange-choose-method = Выберите способ получения { $currency }:
exchange-rate-unavailable = ⚠️ Курс временно недоступен. Попробуйте позже.
exchange-confirm-summary-top = 📋 Проверьте параметры заявки
exchange-confirm-title = Проверьте параметры заявки
exchange-confirm-summary-bottom = Если всё верно, подтвердите создание заявки.
exchange-off-hours-alert = Заявка попадёт в очередь до ближайшего рабочего интервала.
exchange-off-hours-confirmation =
    ⚠️ Менеджеры сейчас не работают.

    Заявка будет передана менеджеру в ближайший рабочий интервал. Создать её можно сейчас — режим работы не влияет на оформление.

    График: { $hours }.

    Если всё верно, нажмите «Да».
exchange-summary-country = Страна
exchange-summary-city = Город
exchange-summary-rate = Курс
exchange-summary-sell = Отдаёте
exchange-summary-buy = Получаете
exchange-summary-method = Способ получения
exchange-rate-from = от
manager-summary-user = Пользователь
atxg-eyebrow = Кошелёк AntEx
atxg-credit-title = ATXG начислены
atxg-debit-title = ATXG списаны
atxg-credit-lead = Средства уже доступны в вашем кошельке.
atxg-debit-lead = Операция отражена в вашем кошельке.
atxg-amount-label = Сумма
atxg-description-label = Основание

## Buttons
btn-confirm = ✅ Подтвердить
btn-start-telegram = 💬 Создать в Telegram
btn-start-miniapp = 📲 Открыть Mini App
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
country-thailand = 🇹🇭 Таиланд
country-vietnam = 🇻🇳 Вьетнам
country-georgia = 🇬🇪 Грузия
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
manager-alert-access-denied = Нет прав
manager-alert-order-not-found = Заявка не найдена
manager-alert-status-changed = Заявка уже изменила статус
manager-alert-client-link-missing = У пользователя нет Telegram-ссылки
manager-alert-card-update-failed = Не удалось обновить карточку заявки
manager-alert-handoff-failed = Заявка принята, но клиенту не удалось отправить инструкцию. Проверьте username менеджера и повторите напоминание.
manager-alert-reminder-processing-only = Напоминание доступно только для заявки в работе
manager-alert-reminder-failed = Не удалось отправить напоминание. Попробуйте ещё раз.
manager-alert-reminder-sent = 🔔 Напоминание отправлено клиенту
manager-alert-cancelled = Заявка отменена
manager-alert-chat-stale = Кнопка чата устарела

## Order statuses
order-created =
    ✅ Заявка №{ $id } создана.

    ⏳ Мы получили ваш запрос и передали его в очередь.

    Ожидайте подтверждения менеджера. Статус заявки обновится автоматически.
order-created-offline =
    ✅ Заявка №{ $id } создана.

    Заявка принята.

    <blockquote>Менеджер начнёт обработку в ближайший рабочий интервал.</blockquote>
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
    Спасибо, что выбрали AntEx!

    За видеоотзыв в формате Telegram-кружка начислим <b>бонус $5 к следующему обмену</b>.

    ⭐ Будем рады отзыву — он помогает делать сервис лучше.
order-cancelled = ❌ Заявка #{ $id } отменена.
manager-chat-open-text = Здравствуйте! Вы оставляли заявку #{ $id } на обмен { $amount } { $currency }. Готовы продолжить?
user-chat-open-text = Здравствуйте! По заявке #{ $id } на сумму { $amount } { $currency } подтверждаю готовность к обмену.
btn-open-client-chat = 💬 Открыть чат с клиентом
btn-remind-client = 🔔 Напомнить клиенту
referral-bonus-credited =
    🎁 Вознаграждение по реферальной программе: +{ $amount } ATXG
    За успешно завершённую заявку #{ $order_id }.
referral-bonus-reversed =
    💸 Вознаграждение по реферальной программе списано: -{ $amount } ATXG
    Заявка #{ $order_id } отменена.
referral-eyebrow = Реферальная программа
referral-credited-title = ATXG начислены
referral-reversed-title = ATXG списаны
referral-credited-lead = Вознаграждение за завершённую заявку уже доступно в кошельке.
referral-reversed-lead = Вознаграждение отменено вместе с заявкой.
referral-amount-label = Сумма
referral-order-label = Заявка
miniapp-aex-referral-reward = Реферальное начисление
miniapp-aex-referral-reward-with-order = Реферальное начисление по заявке { $order_number }
miniapp-aex-withdraw-hold = Зарезервировано
miniapp-aex-withdraw-hold-with-order = Зарезервировано по заявке { $order_number }
miniapp-aex-withdraw-debit = Списано
miniapp-aex-withdraw-debit-with-order = Списано по заявке { $order_number }
miniapp-aex-withdraw-release = Возврат
miniapp-aex-withdraw-release-with-order = Возврат по заявке { $order_number }
