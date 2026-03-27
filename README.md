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

### 6. Заполнить базу начальными данными

```bash
cd back
uv run python app/databases/seed.py
```

Сидирование добавляет стартовые банки и карты.

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

После старта будут доступны:

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Healthcheck: `http://127.0.0.1:8000/health`

## Примечания

- В dev-режиме приложение поднимает Telegram bot в режиме `polling`, поэтому без корректного `TELEGRAM_BOT_TOKEN` запуск может завершиться ошибкой.
- `PROXY` поддерживает форматы `host:port:user:pass` и `http://user:pass@host:port`.
- При временной сетевой ошибке Telegram polling в dev-режиме не падает безвозвратно, а переподключается с backoff.
- Если меняете схему базы, повторно запустите `uv run alembic upgrade head`.
- Если нужны проверки перед коммитом:

```bash
cd back
uv run pytest tests -v
uv run ruff check .
```
