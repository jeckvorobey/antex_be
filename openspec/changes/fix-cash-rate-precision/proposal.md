## Why

Внутренний вычет за cash-доставку сейчас рассчитывается через `float` до
преобразования в `Decimal`. На дробной границе это может изменить `ceil` на
одну единицу валюты получения и дать неверные `amountBuy` и `deliveryRate`.

## What Changes

- Расчёт конверсионного курса `USDT→buy` для cash-вычета выполняется из
  исходных `price` и `margin` в `Decimal` без промежуточного `float`.
- Для всех канонических RUB-пар фиксируется тестовая матрица cash-правила и
  guard, требующий обновить матрицу при изменении набора таких пар.
- Публичный контракт и модель заявки не получают полей внутреннего вычета или
  его конверсионного курса.

## Capabilities

### New Capabilities

- `cash-delivery-rate-precision`: Точный cash-расчёт и его регрессионные
  гарантии для канонических RUB-пар.

### Modified Capabilities

- Нет.

## Impact

- `app/services/cash_delivery_rate.py` и существующие backend-тесты cash quote,
  order-flow и API.
- Новых миграций, DTO, API-полей, изменений Mini App, Admin и Telegram нет.
