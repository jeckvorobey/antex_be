## ADDED Requirements

### Requirement: Manager-only operational API
Система SHALL разрешать manager chat REST API и выдачу одноразового WebSocket ticket только Telegram-пользователю с operator access.

#### Scenario: Обычный пользователь обращается к manager API
- **WHEN** пользователь без operator access вызывает endpoint `/api/manager/*`
- **THEN** система возвращает `403` и не раскрывает manager chat data

#### Scenario: Manager получает одноразовый ticket
- **WHEN** manager запрашивает realtime ticket и WebSocket использует его первый раз до истечения TTL
- **THEN** система принимает соединение, а повторное использование того же ticket отклоняет

### Requirement: Durable Telegram capture
Система SHALL сохранять не обработанные предыдущими workflow routers private Telegram messages, SHALL дедуплицировать повтор по Telegram chat/message identity и SHALL сохранять редакции существующего сообщения.

#### Scenario: Повторная доставка обычного update
- **WHEN** один Telegram message доставлен backend повторно
- **THEN** система сохраняет ровно одно сообщение и одну беседу клиента

#### Scenario: Edited update изменяет сохранённое сообщение
- **WHEN** Telegram присылает edited update для сохранённого сообщения с новым текстом или caption
- **THEN** система добавляет append-only revision и обновляет текущее представление сообщения

#### Scenario: Transient capture failure
- **WHEN** обработка обычного или edited Telegram update завершается transient exception
- **THEN** polling не запрашивает следующий offset, а webhook не отвечает `2xx`, пока capture не завершится успешно, чтобы Telegram мог доставить update повторно

#### Scenario: Unrelated webhook handler failure
- **WHEN** handler вне manager chat capture завершается exception
- **THEN** webhook логирует ошибку и отвечает `2xx`, не запуская повторную доставку update

### Requirement: Atomic unread state
Система SHALL увеличивать unread count атомарно в PostgreSQL для каждого входящего сообщения, кроме случая, когда хотя бы одно живое manager connection просматривает эту беседу.

#### Scenario: Два входящих сообщения обрабатываются конкурирующими сессиями
- **WHEN** две сессии прочитали одинаковый исходный unread count и обе фиксируют входящее сообщение
- **THEN** итоговый unread count увеличивается на два без lost update

#### Scenario: Беседа открыта в одном manager connection
- **WHEN** живое соединение manager просматривает беседу и приходит новое сообщение этой беседы
- **THEN** система сохраняет сообщение без увеличения unread count

### Requirement: Per-connection realtime state
Система SHALL хранить presence и viewing в Redis независимо для каждого `connection_id`, а online/viewing SHALL учитывать живые keys всех backend instances.

#### Scenario: Одно из двух соединений отключается
- **WHEN** у manager есть два живых соединения и одно отключается
- **THEN** система удаляет только keys отключённого соединения и продолжает считать manager online

#### Scenario: Два соединения просматривают разные беседы
- **WHEN** соединения на разных backend instances публикуют viewing для разных conversation IDs
- **THEN** обе беседы одновременно считаются просматриваемыми до очистки или истечения TTL соответствующего connection key

### Requirement: Realtime after persistence
Система SHALL публиковать manager chat events через Redis Pub/Sub после успешного сохранения и SHALL считать REST/PostgreSQL источником восстановления после reconnect.

#### Scenario: Redis publish временно недоступен
- **WHEN** сообщение успешно сохранено, но Redis publish завершается ошибкой
- **THEN** сохранение остаётся успешным, ошибка логируется, а REST reconciliation возвращает сохранённое состояние

### Requirement: Idempotent manager reply
Система SHALL сохранять manager reply с уникальным `clientRequestId`, отправлять его через официальный Telegram bot и сохранять delivery state, включая failure. Ответ на сообщение SHALL передавать Telegram message ID, соответствующий внутреннему `replyToMessageId`.

#### Scenario: HTTP retry повторяет manager reply
- **WHEN** один `clientRequestId` отправлен повторно
- **THEN** система возвращает ранее созданное сообщение и не выполняет вторую Telegram delivery

#### Scenario: Manager отвечает на конкретное сообщение
- **WHEN** manager reply содержит внутренний `replyToMessageId` из текущей беседы
- **THEN** Telegram delivery использует Telegram message ID связанного сообщения как reply target

### Requirement: Durable chat attachments
Система SHALL поддерживать входящие и исходящие photo, document, voice, video, sticker, animation, audio и video note с Telegram file metadata. Bytes исходящего вложения SHALL оставаться в durable storage до подтверждённой доставки или явного удаления.

#### Scenario: Первая отправка вложения завершается transient failure
- **WHEN** bytes и metadata вложения сохранены, а Telegram send завершается transient exception
- **THEN** сообщение остаётся в failed state и повторная попытка может использовать те же сохранённые bytes без повторной загрузки клиентом

#### Scenario: Backend перезапущен после неуспешной доставки вложения
- **WHEN** новый backend instance повторяет delivery по сохранённому `clientRequestId`
- **THEN** система использует PostgreSQL payload, обновляет то же сообщение и не создаёт duplicate

#### Scenario: Повтор уже доставленного вложения
- **WHEN** retry использует `clientRequestId` сообщения в sent state
- **THEN** система возвращает сохранённый результат без повторной Telegram send

#### Scenario: Telegram присылает поддерживаемый media update
- **WHEN** catch-all handler получает один из поддерживаемых media types
- **THEN** система сохраняет корректный message type и полные Telegram file metadata

#### Scenario: Manager скачивает частый Telegram media type
- **WHEN** manager запрашивает protected attachment для sticker, animation, audio или video note
- **THEN** система использует сохранённые file metadata и возвращает bytes через единый download endpoint

### Requirement: Offline manager fallback
Система SHALL отправлять компактное Telegram fallback уведомление manager только при отсутствии живого realtime presence.

#### Scenario: Manager имеет живое соединение
- **WHEN** входящее сообщение сохранено и хотя бы один Redis presence key manager жив
- **THEN** Telegram fallback уведомление не отправляется

### Requirement: Existing order domain rules
Система SHALL выполнять manager order status actions через существующий order status service и notification/write-access helpers.

#### Scenario: Manager меняет статус заявки
- **WHEN** manager вызывает status endpoint для существующей заявки
- **THEN** система применяет существующие переходы статуса и публикует обновление без отдельной chat-specific реализации lifecycle

#### Scenario: Telegram вернул ID status notification
- **WHEN** отправка status notification вернула Telegram message ID
- **THEN** система сохраняет ID независимо от того, изменился ли cached write-access flag

### Requirement: Bounded conversation list queries
Система SHALL обогащать страницу бесед последним сообщением и последней заявкой без отдельной пары SQL queries на каждый элемент страницы.

#### Scenario: Manager загружает страницу из нескольких бесед
- **WHEN** REST API формирует одну страницу списка чатов
- **THEN** количество SQL queries остаётся ограниченным и не растёт линейно на две queries для каждой беседы

### Requirement: Official manager communication flow
Система SHALL направлять клиента к официальному Telegram bot и Manager Mini App и SHALL NOT включать личные `t.me/<manager>` или `tg://user` ссылки в operational notifications, statuses или keyboards.

#### Scenario: Клиент получает operational notification
- **WHEN** bot отправляет сообщение о заявке или контакте с менеджером
- **THEN** доступные действия ведут в bot conversation или Manager Mini App без личной ссылки менеджера

#### Scenario: Клиент начинает официальный чат из активного workflow
- **WHEN** клиент нажимает кнопку начала диалога при активном exchange FSM
- **THEN** система очищает FSM перед следующим сообщением и сохраняет его через manager chat catch-all
