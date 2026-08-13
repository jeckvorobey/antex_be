## Why

Telegram deep link для черновика сообщения кодировал пробелы как `+`. На части клиентов,
включая iOS, такой черновик отображается с искажёнными пробелами.

## What Changes

- Сериализовать query-параметр `text` Telegram chat deep link через percent-encoding.
- Добавить regression-тесты для пробелов, Unicode, переносов строк и специальных символов.

## Impact

- `app/telegram/keyboards.py`
- `tests/telegram/test_start_and_keyboards.py`
