## ADDED Requirements

### Requirement: Percent-encoding черновика Telegram-сообщения
Backend SHALL сериализовать параметр `text` в Telegram chat deep link через percent-encoding,
при котором пробелы представлены как `%20`, а не как `+`.

#### Scenario: Черновик содержит Unicode и специальные символы
- **WHEN** генератор получает черновик с кириллицей, emoji, переносами строк, пробелами,
  `&`, `?` и literal `+`
- **THEN** URL SHALL содержать обратимо закодированный `text`, а URL-decoding SHALL вернуть
  исходный черновик без искажений
