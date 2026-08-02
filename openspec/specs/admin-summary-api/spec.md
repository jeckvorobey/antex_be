# Спецификация совместимости admin summary

## Purpose
Фиксирует обратную совместимость базовых полей admin summary при расширении dashboard.

## Requirements

### Requirement: Расширение admin summary обратно совместимо
Система MUST сохранять существующие поля `ordersToday`, `usersTotal` и `featuredRates` при добавлении расширенной операционной сводки.

#### Scenario: Старый потребитель читает summary
- **WHEN** потребитель использует прежние поля `/api/admin/summary`
- **THEN** прежние поля остаются доступны с прежним смыслом
