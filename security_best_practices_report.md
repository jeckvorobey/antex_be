# Security review: unified Telegram messages

## Итог

Проверен изменённый Python/FastAPI и aiogram scope. Подтверждённых Critical, High,
Medium или Low уязвимостей в изменениях нет.

## Проверенный scope

- `app/telegram/presentation/` — типизированная модель, escaping, компоненты и доставка;
- `app/telegram/messages.py`, handlers и notification services — формирование и отправка
  пользовательских и manager-сообщений;
- `app/modules/broadcasts/schemas.py` — ограничение размера административной рассылки.

## Подтверждённые защитные меры

- **SEC-001 — закрыт.** Динамические поля экранируются перед попаданием в Telegram HTML:
  `app/telegram/presentation/escaping.py:10`,
  `app/telegram/presentation/components.py:38`.
- **SEC-002 — закрыт.** Rich/regular fallback выполняется ровно один раз и только при
  подтверждённой несовместимости Telegram API; ошибки транспорта не маскируются:
  `app/telegram/presentation/delivery.py:43`.
- **SEC-003 — закрыт.** Свободный комментарий site lead ограничен 1 000 символами, а payload
  административной рассылки валидируется до 4 096 символов:
  `app/services/site_lead_notifications.py:60`,
  `app/modules/broadcasts/schemas.py:12`.
- **SEC-004 — закрыт.** Логи доставки не содержат тело сообщения, токены или HTML; в них
  остаются только технические идентификаторы и тип операции.

## Остаточный риск

Реальная поддержка Rich Messages зависит от версии Telegram Bot API на production. При
несовместимости применяется проверяемый regular HTML fallback; тесты покрывают запрет двойной
доставки. Неизменённые API-auth/CORS/deployment настройки не входили в этот diff-аудит.

## Проверки

`uv run pytest tests -q` — 575 passed; `uv run ruff check .` и
`uv run ruff format --check .` — успешно.
