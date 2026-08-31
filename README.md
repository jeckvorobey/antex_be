# FastAPI backend

## Запуск в разработке

### 1. Предварительные требования

- Python `3.13+`
- `uv`
- PostgreSQL
- Redis

### 2. Установка зависимостей

```bash
cd back
uv sync --extra dev
```

### 3. Подготовка переменных окружения

Создайте локальный `.env` на основе примера:

```bash
cd back
cp .env.example .env
```

Минимум, что нужно проверить в `.env` перед первым запуском:

- `DATABASE_URL` указывает на локальный PostgreSQL
- `REDIS_URL` указывает на локальный Redis
- `TELEGRAM_BOT_TOKEN` заполнен валидным токеном
- `TELEGRAM_MODE=polling` для локальной разработки
- если доступ к `api.telegram.org` ограничен, можно задать `PROXY`
- `CURRENCYBEACON_API_KEY` заполнен валидным ключом для обновления рыночных курсов

По умолчанию backend запускается на `APP_HOST` / `APP_PORT` из `.env`.

### 4. Поднять PostgreSQL и Redis

Нужны доступные локально сервисы:

- PostgreSQL на значении из `DATABASE_URL`
- Redis на значении из `REDIS_URL`

Если используете значения из `.env.example`, это:

- PostgreSQL: `localhost:5432`, база `antex`
- Redis: `localhost:6379`

### 5. Применить миграции

```bash
cd back
uv run alembic upgrade head
```

Проверить SQL без подключения к базе:

```bash
cd back
uv run alembic upgrade head --sql
```

### 6. Заполнить базу начальными данными

```bash
cd back
uv run python app/databases/seed.py
```

Перед сидированием задайте `ADMIN_BOOTSTRAP_PASSWORD` с уникальным паролем.
Сидирование создаёт администратора `admin` только с этим паролем.
Банки, карты, города, менеджеры и курсы нужно добавить отдельно через админку,
миграции или отдельный seed-скрипт.

### 7. Запуск backend

```bash
cd back
uv run python run.py
```

Полезные варианты запуска:

```bash
cd back
uv run python run.py --no-reload
uv run python run.py --host 0.0.0.0 --port 8000
```

Если локально проверяете Telegram bot в `TELEGRAM_MODE=polling`, используйте
`uv run python run.py --no-reload`. Polling допускает только один активный
процесс на один bot token; запуск с автоперезагрузкой или второй локальный
backend может дать конфликт `terminated by other getUpdates request`.
В production polling защищен Redis-lock: если во время deploy коротко
поднимается второй backend, он не вызывает `getUpdates`, пока lock удерживает
активный процесс. Для постоянной работы всё равно держите одну replica на bot
token.

После старта будут доступны:

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Healthcheck: `http://127.0.0.1:8000/health`

Логи пишутся в stdout/stderr для платформенных логов и в ротируемый файл
`LOG_DIR/api.log` только для `WARNING`/`ERROR`. Основные переменные:
`LOG_LEVEL`, `LOG_DIR`, `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT`.
Во время pytest file logging в рабочий `LOG_DIR/api.log` отключается, поэтому
mock-ошибки тестов не должны попадать в runtime log. Для проверки самого file
logging тесты используют временный каталог.
В production Docker image задан `HEALTHCHECK` через `curl` на `/health`.

## Источник курсов

- Основной источник рыночных курсов: `CurrencyBeacon`
- Backend запрашивает `USD -> USDT,RUB,THB,GEL,VND` и строит из них пары:
  `USDTTHB`, `USDTGEL`, `USDTVND`, `RUBTHB`, `RUBGEL`, `RUBVND`
- Если `CurrencyBeacon` не возвращает валидный `RUB`, backend дозапрашивает
  `USD/RUB` через бесплатный `Frankfurter` fallback и продолжает пересчёт
  RUB-пар.
- Переменные окружения:
  - `CURRENCYBEACON_API_KEY`
- Логика наценки хранится отдельно в `Rates.margin` и не зависит от провайдера

## Диагностика и сброс локальной dev-БД

Если локальная база не совпадает с текущими моделями, пересоздайте dev-БД и
примените миграции с нуля:

```bash
cd back
dropdb antex
createdb antex
uv run alembic upgrade head
uv run python app/databases/seed.py
```

После reset в схеме должны быть:

- колонка `Rates.margin` с default `3.0`;
- таблица `Broadcasts`.

Минимальная проверка миграций:

```bash
cd back
uv run alembic upgrade head --sql
uv run alembic upgrade head
uv run python app/databases/seed.py
```

## Примечания

- В сценарии принятия заявки используется один менеджер из `UserRepository.get_manager()`.
  Для кнопки «Написать менеджеру» с подготовленным текстом у его Telegram-аккаунта должен быть
  публичный `username`; без него заявка останется «В работе», а менеджер увидит честное
  предупреждение и сможет повторить напоминание после исправления настройки.
- Клиентский handoff и напоминание сначала используют Telegram Rich Message, а при отказе
  совместимости Bot API однократно отправляются как эквивалентный HTML. Общие правила проекта
  остаются в `../antex_rules.md` (SSOT), а контракт карточек и Tone of Voice описаны в
  [`docs/telegram-order-messages.md`](docs/telegram-order-messages.md).
- В dev-режиме приложение поднимает Telegram bot в режиме `polling`, поэтому без корректного `TELEGRAM_BOT_TOKEN` запуск может завершиться ошибкой.
- `PROXY` поддерживает форматы `host:port:user:pass` и `http://user:pass@host:port`.
- При временной сетевой ошибке Telegram polling в dev-режиме не падает безвозвратно, а переподключается с backoff.
- Если меняете схему базы, повторно запустите `uv run alembic upgrade head`.
- Актуальный контракт miniapp/admin API описан в `docs/api-contract.md`.
- Если обновление курсов падает из-за провайдера, сейчас backend только логирует ошибку и повторяет попытку по TTL без fallback на последний сохранённый курс.
- Если нужны проверки перед коммитом:

```bash
cd back
uv run pytest tests -v
uv run ruff check .
```
