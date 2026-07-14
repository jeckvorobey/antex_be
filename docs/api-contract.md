# API contract для MVP обмена

## Miniapp

Miniapp использует backend-driven namespace `/api/miniapp/*`.

- `GET /api/miniapp/home` возвращает профиль, быстрые действия, featured rates,
  баннер, сервисы и города для главного экрана.
- `GET /api/miniapp/aex/referral` возвращает ATXG referral payload для страницы
  рефералов: `referralCode`, готовую `referralLink` вида
  `https://t.me/<bot_username>?startapp=ref_<code>`, `totalReferrals` и
  `programConfig` (`referralPercent`, `referralMinWithdraw`,
  `referralMaxWithdraw`, `aexRate`, `aexWithdrawLimit`). `aexWithdrawLimit`
  задает ATXG-порог, после достижения которого miniapp может показывать ATXG как
  доступную внутреннюю валюту рядом с RUB и USDT. Персональный список referrals
  не возвращается.
- `GET /api/miniapp/aex/referrals` возвращает пагинированный безопасный список
  приглашенных пользователей в envelope `items`, `total`, `limit`, `offset`,
  `hasMore`, а также `totalAccrued` и `rewardPercent`. Item не содержит телефон,
  `telegram_id` или сумму заработка по конкретному пользователю.
- `GET /api/miniapp/aex/transactions` возвращает историю ATXG операций в envelope
  `items`, `total`, `limit`, `offset`, `hasMore`. Для `referral_reward`
  описание операции возвращается на русском с публичным номером заявки
  `Order.publicNumber`, без внутреннего `Order.id`.
- `GET /api/miniapp/exchange` возвращает начальное состояние калькулятора,
  chips, доступные пары и стартовый quote.
- `GET /api/miniapp/exchange/quote?currencySell=&currencyBuy=&amountSell=`
  рассчитывает quote на сервере. Клиент не считает итоговый курс сам.
- `POST /api/miniapp/orders` принимает `cityId` опционально, валюты, сумму,
  контакт и метод получения. Сервер сам выбирает город по порядку:
  `cityId` из payload, затем `user.city_id`, затем первый доступный город.
- Для вывода внутреннего токена `POST /api/miniapp/orders` принимает
  `currencySell = ATXG` и локальные валюты получения `THB`, `GEL`, `VND`;
  расчет и проверка пары выполняются через соответствующую USDT-based пару.
- `POST /api/miniapp/orders` возвращает полный `MiniappOrderItem`.
  Клиентские `rate` и `amountBuy`, если переданы, игнорируются.

Machine-readable коды ошибок miniapp:

- `RATE_UNAVAILABLE`
- `UNSUPPORTED_PAIR`
- `CITY_NOT_FOUND`
- `ORDER_ALREADY_EXISTS`

## Admin

Обычные административные endpoints принимают только access token с типом `admin`.
Refresh token с типом `admin_refresh` допускается исключительно на
`POST /api/admin/refresh` и не авторизует CRUD/marketing операции.

- `GET/PATCH /api/admin/config` возвращает и обновляет `enabled`, timestamps и
  настройки referral program: `referralPercent`, `referralMinWithdraw`,
  `referralMaxWithdraw`, `aexRate`, `aexWithdrawLimit`.
- `GET /api/admin/summary` возвращает метрики dashboard:
  `ordersToday`, `usersTotal`, `rubThbRate`.
- `GET /api/admin/rates` возвращает административное представление курсов:
  базовый `price` и `margin` по каждой паре.
- `PATCH /api/admin/rates/{rate_id}` позволяет менять `margin` конкретной пары.
- `GET /api/admin/orders` возвращает список заявок с пользователем и городом.
- `PATCH /api/admin/orders/{order_id}/status` меняет статус заявки и возвращает
  обновлённую заявку.

## Marketing Management

Все endpoints защищены admin access token типа `admin` и используют prefix
`/api/admin/marketing`; `admin_refresh` отклоняется.

- `POST /campaigns/code-preview` — выдаёт незаписанный code длиной 10 символов
  `A-Z0-9` и короткоживущий подписанный `token`. Операция не создаёт campaign или
  reservation rows в БД.
- `POST /campaigns` — атомарно создаёт кампанию. Новый admin flow передаёт
  `codeToken` из preview response; backend проверяет подпись, тип, срок и сохраняет
  embedded code вместе с валидной кампанией. Для обратной совместимости request без
  `codeToken` получает новый server-generated code. Response возвращает `link` вида
  `https://t.me/<bot>?startapp=market_<CODE>` и `marketParameter` вида
  `market=<CODE>`. Прямое поле `code` в request запрещено.
- `GET /campaigns` — список `items/total/limit/offset`; filters: `search`,
  `provider`, `status`, `limit`, `offset`. Item содержит `attributedUsers` и
  `applications`, рассчитанные без N+1.
- `GET /campaigns/{id}` — карточка кампании.
- `PATCH /campaigns/{id}` — изменение metadata/status; `code` и `provider`
  неизменяемы. Удаление заменено status `archived`.
- `PUT /campaigns/{id}/daily-metrics/{YYYY-MM-DD}` — идемпотентный upsert
  non-negative `impressions`, `starts`, `spend`, optional `platformCpm`.
- `GET /applications` — агрегаты заявок по компаниям с filters `dateFrom`,
  `dateTo`, `campaignId`, `provider`, `status`, `currency`, `limit`, `offset`.
- `GET /dashboard` — `summary`, `funnel`, zero-filled `timeSeries`,
  `campaignComparison`, `spendByCurrency`, `appliedFilters`.

First-touch attribution создаётся только из `start_param=market_<CODE>` после
успешной backend-проверки Telegram initData. Один user закрепляется максимум за
одной первой активной кампанией; повторные links не меняют attribution. Ошибка,
unknown или archived code не блокируют обычную Telegram auth. Browser URL сам по
себе не является доверенным источником.

Заявка относится к кампании через user attribution, только если `Order.createdAt`
не раньше `attributed_at`. `applications` считает все заявки, `uniqueApplicants`
— уникальных пользователей, `completedApplications` — заявки в completed status.
`attributionToApplicationRate = uniqueApplicants / attributedUsers * 100`,
`applicationCompletionRate = completedApplications / applications * 100`;
деление на ноль возвращает `null`. Расходы разных currencies не складываются:
без currency filter `spendTotal` равен `null`, а суммы возвращаются в
`spendByCurrency`. ROI/ROAS не рассчитываются.

Machine-readable marketing errors:

- `UNIQUE_CODE_EXHAUSTED`
- `INVALID_MARKETING_CODE_PREVIEW`
- `MARKETING_CODE_ALREADY_EXISTS`
- `TELEGRAM_BOT_USERNAME_REQUIRED`
- `INVALID_MARKETING_CODE`
- `MARKETING_CAMPAIGN_NOT_FOUND`
- `MARKETING_CAMPAIGN_INACTIVE`
- `INVALID_CAMPAIGN_DATES`
- `INVALID_MARKETING_DATE_RANGE`
- `UNSUPPORTED_MARKETING_PROVIDER`
- `UNSUPPORTED_CAMPAIGN_STATUS`
