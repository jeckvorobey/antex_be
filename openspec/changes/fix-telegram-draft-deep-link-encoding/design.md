## Context

`_chat_url_with_draft()` добавляет черновик в query параметр `text` для `t.me` и
`tg://resolve`. Стандартный form-encoding передаёт пробел как `+`, а Telegram deep link
должен использовать percent-encoding.

## Decision

Передать `quote_via=quote` в существующие вызовы `urlencode()`. Это сохраняет единый
генератор URL для всех клиентов без ручной замены символов или platform-specific ветвлений.

## Verification

Regression-тест проверяет raw URL и обратное decoding исходного текста. Полный backend
набор и Ruff подтверждают отсутствие регрессий Telegram keyboard flow.
