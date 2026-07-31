## ADDED Requirements

### Requirement: Успешная авторизация фиксирует активность пользователя
Система SHALL обновлять `lastActiveAt` пользователя только после успешной Telegram-аутентификации.

#### Scenario: Пользователь успешно входит в Mini App
- **WHEN** Telegram init data успешно проверены
- **THEN** `lastActiveAt` пользователя обновляется текущим временем
