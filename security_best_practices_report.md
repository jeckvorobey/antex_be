# Security and Complexity Review

Дата: 2026-06-30
Область: незакоммиченные backend-файлы в `back/`

## Итог

Критичных и высоких незакрытых security findings в просмотренной области не
обнаружено. Найден и исправлен один риск утечки чувствительных данных в логах и
одна лишняя сетевая операция в polling lifecycle.

## Findings

### SEC-1: Telegram identity lookup мог логировать proxy credentials

- Статус: исправлено
- Риск: Medium
- Файл: `app/telegram/bot.py`
- Область: `_get_safe_bot_identity()`

До исправления ошибка `bot.get_me()` логировалась с traceback. Для сетевых
ошибок это могло вывести proxy URL с credentials из exception message. Сейчас
логируется только тип ошибки:

```text
Failed to load Telegram bot identity: error_type=<ExceptionClass>
```

Тест: `tests/telegram/test_bot_lifecycle.py::test_safe_bot_identity_failure_does_not_log_proxy_url`.

### PERF-1: Повторный `get_me()` при polling retry/conflict logs

- Статус: исправлено
- Риск: Low
- Файл: `app/telegram/bot.py`
- Область: `_get_safe_bot_identity()`

Если aiogram `Bot` не имел локальных `id`/`username`, safe identity могла
запрашиваться через Telegram API при каждом повторном логировании polling
startup/conflict. Добавлен lifecycle cache `_bot_identity_cache`, который
сбрасывается при `init_bot()` и `stop_bot()`.

Тест: `tests/telegram/test_bot_lifecycle.py::test_safe_bot_identity_uses_cached_get_me_result`.

## Проверки

Выполнено:

```bash
uv run pytest tests/telegram/test_bot_lifecycle.py -q
uv run pytest tests -v
uv run ruff check .
```

Результат полного backend suite: `186 passed, 15 warnings`.
