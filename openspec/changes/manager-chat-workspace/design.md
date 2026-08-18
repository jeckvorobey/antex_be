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

Catch-all handlers регистрируются после доменных routers. Ошибка persistence/capture оборачивается в отдельный retry-маркер. В polling custom Dispatcher обрабатывает updates последовательно и пробрасывает этот маркер до цикла до следующего запроса `getUpdates`, поэтому offset не сдвигается. Webhook синхронно ожидает `feed_update` и возвращает non-2xx только для retry-маркера; unrelated handler exceptions логируются и подтверждаются `2xx`, сохраняя прежнюю защиту от retry storm. Dedupe по Telegram chat/message identity делает повтор безопасным. Простого повторного `raise` внутри handler недостаточно: стандартный polling Dispatcher aiogram проглатывает exception как обработанный, а webhook timeout переводит handler в фон и отвечает `200`.

### Unread увеличивается SQL-выражением

Repository выполняет `unread_count = unread_count + 1` в БД и обновляет ORM snapshot. Это сохраняет оба результата при конкурирующих сессиях, в отличие от Python read-modify-write.

### Presence и viewing имеют key на connection

Каждое соединение пишет TTL keys `presence:<manager_id>:<connection_id>` и `viewing:<manager_id>:<connection_id>`. Проверки используют неблокирующий Redis scan по manager prefix; disconnect удаляет только свои keys. Это работает между backend instances и не требует локального process state как источника истины.

### Manager order actions переиспользуют доменные services

REST router вызывает существующий `order_status` flow и notification helpers. Дублирование status transitions в chat service запрещено.

### Исходящие вложения сохраняются в PostgreSQL до Telegram delivery

При первой загрузке message, metadata и bytes фиксируются отдельным commit до внешнего
Telegram API side effect. Failed/pending delivery повторяется по тому же `clientRequestId`
из database payload, включая после restart другого backend instance; sent message повторно
не отправляется. Payload очищается только после подтверждённой доставки. Локальная файловая
система отвергнута как multi-instance unsafe, а external object storage остаётся v1 non-goal.

### Страница бесед обогащается bulk-запросами

Repository загружает последние сообщения страницы и последние заявки пользователей двумя
ограниченными bulk-контрактами. Serializer не выполняет SQL внутри item-loop, поэтому query
count не растёт на пару message/order queries для каждой беседы.

### Operational communication использует только official surfaces

Клиент начинает диалог callback-кнопкой в текущем официальном bot chat; callback очищает
активный exchange FSM, после чего catch-all сохраняет сообщение. Менеджер открывает заявки и
чаты только через Manager Mini App `web_app`. Персональные `t.me/<manager>` и `tg://user`
не используются в operational notifications, status cards или keyboards.

## Risks / Trade-offs

- [Redis outage] → persistence не блокируется; publish логируется, клиент восстанавливает состояние через REST.
- [Abrupt WebSocket loss] → connection keys могут жить до 45 секунд; TTL ограничивает ложный online/viewing.
- [Scan cost] → scope содержит одного менеджера и малое число живых sockets; per-connection keys важнее глобального перезаписываемого key.
- [Повтор Telegram update] → уникальная Telegram identity и `clientRequestId` обеспечивают idempotency.
- [Детерминированная ошибка capture блокирует polling очередь] → update остаётся неподтверждённым и повторяется с bounded backoff; причина видна в error logs и требует operational исправления вместо потери данных.

## Migration Plan

1. Применить `031_add_order_delivery_rate` из актуального `dev`.
2. Применить `032_add_manager_chat_workspace` и создать chat tables/indexes/constraints.
3. Применить `033_add_chat_attachment_payload` для durable bytes и nullable pending Telegram file id.
4. Применить `034_add_chat_attachment_metadata` для media-specific JSON metadata.
5. Запустить backend с manager API, Telegram capture и Redis realtime subscriber.
6. При rollback сначала остановить новый runtime, затем последовательно выполнить `034 -> 033 -> 032 -> 031`; cash-rate schema остаётся установленной.

## Open Questions

Нет.
