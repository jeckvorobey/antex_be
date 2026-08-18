## Context

Backend уже обслуживает Telegram bot, Mini App и lifecycle заявок. Manager chat добавляет постоянное состояние и realtime transport, не меняя source of truth: сообщения и unread живут в PostgreSQL, а Redis хранит только короткоживущие tickets, Pub/Sub и состояние WebSocket connections.

Feature-ветка синхронизирована с `dev`, где revision `031` добавляет `Orders.deliveryRate`; поэтому manager chat следует за ней revision `032`.

## Goals / Non-Goals

**Goals:**

- Не терять обычные и edited Telegram updates при transient backend failure.
- Сохранить историю, редакции, unread и delivery state в PostgreSQL.
- Дать manager-only REST/WebSocket API с межинстансным realtime через Redis.
- Считать presence/viewing по каждому `connection_id` и не терять конкурентные unread increments.
- Сохранить существующую доменную логику заявок и Telegram write-access.

**Non-Goals:**

- Несколько менеджеров, assignment/claim/queue и typing indicators.
- Customer presence и full-text message search.
- Замена PostgreSQL realtime-состоянием или периодический polling.

## Decisions

### PostgreSQL остаётся source of truth

Conversation, message, revision и attachment metadata сохраняются до realtime publish. Redis Pub/Sub ускоряет доставку событий, но reconnect выполняет reconciliation через REST. Альтернатива с Redis-only history отвергнута из-за потери данных при restart/outage.

### Telegram update подтверждается только после успешного capture

Catch-all handlers регистрируются после доменных routers. Ошибка persistence/capture оборачивается в отдельный retry-маркер. В polling custom Dispatcher обрабатывает updates последовательно и пробрасывает этот маркер до цикла до следующего запроса `getUpdates`, поэтому offset не сдвигается. Webhook синхронно ожидает `feed_update` и при retry-маркере возвращает non-2xx. Dedupe по Telegram chat/message identity делает повтор безопасным. Простого повторного `raise` внутри handler недостаточно: стандартный polling Dispatcher aiogram проглатывает exception как обработанный, а webhook timeout переводит handler в фон и отвечает `200`.

### Unread увеличивается SQL-выражением

Repository выполняет `unread_count = unread_count + 1` в БД и обновляет ORM snapshot. Это сохраняет оба результата при конкурирующих сессиях, в отличие от Python read-modify-write.

### Presence и viewing имеют key на connection

Каждое соединение пишет TTL keys `presence:<manager_id>:<connection_id>` и `viewing:<manager_id>:<connection_id>`. Проверки используют неблокирующий Redis scan по manager prefix; disconnect удаляет только свои keys. Это работает между backend instances и не требует локального process state как источника истины.

### Manager order actions переиспользуют доменные services

REST router вызывает существующий `order_status` flow и notification helpers. Дублирование status transitions в chat service запрещено.

## Risks / Trade-offs

- [Redis outage] → persistence не блокируется; publish логируется, клиент восстанавливает состояние через REST.
- [Abrupt WebSocket loss] → connection keys могут жить до 45 секунд; TTL ограничивает ложный online/viewing.
- [Scan cost] → scope содержит одного менеджера и малое число живых sockets; per-connection keys важнее глобального перезаписываемого key.
- [Повтор Telegram update] → уникальная Telegram identity и `clientRequestId` обеспечивают idempotency.
- [Детерминированная ошибка capture блокирует polling очередь] → update остаётся неподтверждённым и повторяется с bounded backoff; причина видна в error logs и требует operational исправления вместо потери данных.

## Migration Plan

1. Применить `031_add_order_delivery_rate` из актуального `dev`.
2. Применить `032_add_manager_chat_workspace` и создать chat tables/indexes/constraints.
3. Запустить backend с manager API, Telegram capture и Redis realtime subscriber.
4. При rollback сначала остановить новый runtime, затем downgrade `032 -> 031`; cash-rate schema остаётся установленной.

## Open Questions

- Durable storage и retry policy для исходящих вложений уточняются в оставшихся remediation tasks.
