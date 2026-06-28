# API contract для MVP обмена

## Miniapp

Miniapp использует backend-driven namespace `/api/miniapp/*`.

- `GET /api/miniapp/home` возвращает профиль, быстрые действия, featured rates,
  баннер, сервисы и города для главного экрана.
- `GET /api/miniapp/aex/referral` возвращает AEX referral payload для страницы
  рефералов: `referralCode`, готовую `referralLink` вида
  `https://t.me/<bot_username>?startapp=ref_<code>`, `totalReferrals` и
  `programConfig` (`referralPercent`, `referralMinWithdraw`,
  `referralMaxWithdraw`, `aexRate`). Персональный список referrals не
  возвращается.
- `GET /api/miniapp/aex/transactions` возвращает историю AEX операций в envelope
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
- `POST /api/miniapp/orders` возвращает полный `MiniappOrderItem`.
  Клиентские `rate` и `amountBuy`, если переданы, игнорируются.

Machine-readable коды ошибок miniapp:

- `RATE_UNAVAILABLE`
- `UNSUPPORTED_PAIR`
- `CITY_NOT_FOUND`
- `ORDER_ALREADY_EXISTS`

## Admin

- `GET/PATCH /api/admin/config` возвращает и обновляет `enabled`, timestamps и
  настройки referral program: `referralPercent`, `referralMinWithdraw`,
  `referralMaxWithdraw`, `aexRate`.
- `GET /api/admin/summary` возвращает метрики dashboard:
  `ordersToday`, `usersTotal`, `rubThbRate`.
- `GET /api/admin/rates` возвращает административное представление курсов:
  базовый `price` и `margin` по каждой паре.
- `PATCH /api/admin/rates/{rate_id}` позволяет менять `margin` конкретной пары.
- `GET /api/admin/orders` возвращает список заявок с пользователем и городом.
- `PATCH /api/admin/orders/{order_id}/status` меняет статус заявки и возвращает
  обновлённую заявку.
