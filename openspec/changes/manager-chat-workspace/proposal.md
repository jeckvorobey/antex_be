## Why

Менеджеру нужен надёжный operational chat внутри Telegram Mini App: клиентские сообщения должны сохраняться без потерь, а REST/WebSocket API — давать единое состояние диалогов, заявок, unread и доставки между несколькими backend instances.

## What Changes

- Добавить постоянные беседы, сообщения, редакции и метаданные вложений в PostgreSQL.
- Добавить защищённый manager REST API и WebSocket transport с одноразовыми Redis tickets.
- Захватывать обычные и edited private Telegram updates после существующих workflow handlers с dedupe и redelivery при transient failure.
- Доставлять ответы через официального Telegram bot и публиковать realtime-события после сохранения.
- Хранить presence/viewing отдельно для каждого WebSocket connection в Redis и атомарно обновлять unread.
- Сохранить Telegram fallback уведомление, когда у менеджера нет живого realtime connection.

## Capabilities

### New Capabilities

- `manager-chat-backend`: постоянное хранение manager chat, manager REST/WebSocket API, Telegram capture, realtime presence/viewing и гарантии конкурентности.

### Modified Capabilities

Нет.

## Impact

- Backend: модели и Alembic migration, repositories, services, manager API router, Telegram handlers и lifespan.
- PostgreSQL остаётся source of truth; Redis используется для tickets, Pub/Sub и TTL-состояния каждого соединения.
- Публичные интеграции: `/api/manager/*`, `/api/manager/realtime/ws`, Telegram bot update processing.
