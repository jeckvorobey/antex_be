## ADDED Requirements

### Requirement: Операционная сводка содержит данные dashboard
Система SHALL одним admin summary ответом возвращать метрики пользователей и заявок, очередь внимания, обороты по валютам и полный список курсов.

#### Scenario: Администратор запрашивает сводку
- **WHEN** авторизованный администратор запрашивает `/api/admin/summary`
- **THEN** ответ содержит структуры `users`, `orders`, `attentionOrders`, `turnover`, `rates` и `generatedAt`

### Requirement: Курс содержит базовую и итоговую цену
Система SHALL возвращать для каждого элемента `rates` и `featuredRates` поля `baseRate`, `baseRateDisplay`, `finalRate` и `finalRateDisplay` в одной display-ориентации.

#### Scenario: Dashboard показывает базовую цену
- **WHEN** admin summary содержит настроенную валютную пару
- **THEN** элемент курса содержит человекочитаемую базовую цену отдельно от итоговой клиентской цены
