## Результат проверки

- Targeted summary/auth/migration pytest: `4 passed`.
- Ruff по всем затронутым backend-файлам: пройден.
- Alembic `upgrade head --sql`: пройден до revision `028`.
- Полный pytest без proxy-переменных: `521 passed`, `3 failed`.

Три оставшихся падения существуют вне dashboard-изменений:

1. referral integration ожидает внутренний `USDTRUB`, которого нет в test seed;
2. `tests/services/test_aex.py` использует неимпортированный `AntExException`;
3. order-status test ожидает устаревший аргумент `currency_buy`.

Полный Ruff также останавливается на существующих ошибках `tests/services/test_aex.py`; затронутые файлы проходят Ruff полностью.

## Уточнение интерфейсного контракта

- `featuredRates` и `rates` дополнены `baseRate` и `baseRateDisplay`.
- Контрактный dashboard pytest: `1 passed` (`9 deselected`).
- Ruff по затронутым backend-файлам: пройден.
- `openspec validate expanded-admin-dashboard --strict`: пройден.
- Финальный Codex review: замечание по точности `RUBUSDT` исправлено RED-тестом; повторная проверка чистая.
