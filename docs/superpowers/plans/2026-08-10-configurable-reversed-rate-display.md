# Configurable Reversed Rate Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить настраиваемую обратную ориентацию отображения курса во всех заявочных интерфейсах без изменения направления обмена и с расчётом по точному прямому курсу.

**Architecture:** `Rates.display_reversed` становится единственным источником настройки представления. Доменный сервис возвращает отдельно точный прямой `rate` для расчёта и `rate_display/rate_text` для UI; при создании заявки backend повторно рассчитывает сумму и сохраняет снимок отображаемого курса, чтобы история и Telegram-карточки не зависели от будущих настроек пары.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, pytest, Vue 3, Quasar, TypeScript, Vitest.

## Global Constraints

- Все рабочие ветки создаются от актуального `main`.
- В `Orders.rate` хранится точный прямой расчётный курс; обратный курс не участвует в вычислениях.
- Для существующих пар миграция включает обратный показ у `RUBTHB`, `RUBGEL`, `RUBUSDT`; остальные пары сохраняют прямой показ.
- Новые и существующие заявки должны иметь стабильное представление курса после изменения настройки пары.
- Backend является SSOT форматирования; клиенты не вычисляют обратный курс самостоятельно.

---

### Task 1: Persistence and configurable rate presentation

**Files:**
- Create: `alembic/versions/030_add_rate_display_and_order_snapshot.py`
- Modify: `app/models/rate.py`
- Modify: `app/models/order.py`
- Modify: `app/schemas/rate.py`
- Modify: `app/api/routers/admin.py`
- Test: `tests/services/test_exchange_service.py`
- Test: `tests/api/test_exchange_contracts.py`

**Interfaces:**
- Produces: `Rate.display_reversed: bool`; `Order.displayRate`, `Order.displayCurrencySell`, `Order.displayCurrencyBuy`; admin request field `displayReversed` and response field `isReversed`.

- [ ] **Step 1: Write failing model, service, and admin-contract tests**

Add tests proving the flag, not a hard-coded pair list, controls orientation; migration defaults and API updates preserve direct rate fields.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run pytest tests/services/test_exchange_service.py tests/api/test_exchange_contracts.py -q`

Expected: FAIL because the persistence fields and configurable request contract do not exist.

- [ ] **Step 3: Add migration, ORM fields, and admin schemas**

The migration adds `Rates.display_reversed` with a false server default, enables it for the three existing reversed pairs, adds nullable order snapshot columns, and backfills snapshots from stored direct order rates. Downgrade removes only the new columns.

- [ ] **Step 4: Replace hard-coded orientation with `Rate.display_reversed`**

All display helpers consume a `Rate` instance and use its flag; calculation helpers continue to consume the direct stored price.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `uv run pytest tests/services/test_exchange_service.py tests/api/test_exchange_contracts.py -q`

Expected: PASS.

### Task 2: Exact quotes and immutable order display snapshots

**Files:**
- Modify: `app/services/exchange.py`
- Modify: `app/services/order_flow.py`
- Modify: `app/schemas/miniapp.py`
- Modify: `app/schemas/order.py`
- Modify: `app/telegram/order_cards.py`
- Test: `tests/services/test_exchange_service.py`
- Test: `tests/services/test_order_flow.py`
- Test: `tests/api/test_miniapp_contract.py`
- Test: `tests/telegram/test_messages.py`

**Interfaces:**
- Produces: exact `ExchangeQuote.rate`; presentation `ExchangeQuote.display_rate`, `display_currency_sell`, `display_currency_buy`, `rate_display`, `rate_text`; order DTO fields `rateDisplay` and `rateText`.

- [ ] **Step 1: Write failing quote, persistence, API, and Telegram tests**

Use a direct RUB/GEL client rate whose exact value is not representable with two decimals. Assert that the amount uses the unrounded direct value while text shows the reciprocal, and that changing the pair flag after order creation does not alter the saved order text.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run pytest tests/services/test_exchange_service.py tests/services/test_order_flow.py tests/api/test_miniapp_contract.py tests/telegram/test_messages.py -q`

Expected: FAIL because quote display is direct, external order values are trusted from the client, and no snapshot exists.

- [ ] **Step 3: Implement exact domain quote and server-side order recomputation**

Add an unrounded calculation-rate helper, keep two-decimal formatting only at presentation boundaries, recompute every external order from current server rates, and save the display snapshot with the order.

- [ ] **Step 4: Expose and render the saved order presentation**

Return `rateDisplay/rateText` from Mini App and admin order DTOs. Telegram cards use saved display fields and fall back to the historical direct rate only for legacy rows without a snapshot.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `uv run pytest tests/services/test_exchange_service.py tests/services/test_order_flow.py tests/api/test_miniapp_contract.py tests/telegram/test_messages.py -q`

Expected: PASS.

### Task 3: Mini App consumes backend presentation

**Files:**
- Modify: `antex_twa/src/types/miniapp.ts`
- Modify: `antex_twa/src/utils/exchange.ts`
- Test: `antex_twa/tests/unit/exchange-utils.spec.ts`
- Test: `antex_twa/tests/unit/exchange.store.spec.ts`

**Interfaces:**
- Consumes: exact pair `calculationRate` plus backend `rateDisplay/rateText`.
- Produces: local quote with exact direct `rate` and unchanged backend presentation.

- [ ] **Step 1: Write a failing local-quote test**

Assert that `RUB/GEL` uses the exact `calculationRate` for `amountBuy` while retaining `1 GEL = … RUB` from the backend.

- [ ] **Step 2: Run the test and verify RED**

Run: `npm test -- --run tests/unit/exchange-utils.spec.ts tests/unit/exchange.store.spec.ts`

Expected: FAIL because local quote reconstructs direct `rateDisplay/rateText`.

- [ ] **Step 3: Reuse pair presentation in local quotes**

Copy `pair.rateDisplay` and `pair.rateText`; keep `rate` equal to `pair.calculationRate`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `npm test -- --run tests/unit/exchange-utils.spec.ts tests/unit/exchange.store.spec.ts`

Expected: PASS.

### Task 4: Admin controls and order display

**Files:**
- Modify: `antex_adm/src/pages/RatesPage.vue`
- Modify: `antex_adm/src/pages/OrdersPage.vue`
- Test: `antex_adm/tests/unit/pages/RatesPage.spec.ts`
- Test: `antex_adm/tests/unit/pages/RatesPage.formatting.spec.ts`
- Create: `antex_adm/tests/unit/pages/OrdersPage.rate-display.spec.ts`

**Interfaces:**
- Consumes: `isReversed`, PATCH `displayReversed`, order `rateDisplay/rateText`.
- Produces: user-visible toggle per pair and stable formatted rate in desktop/mobile order tables.

- [ ] **Step 1: Write failing UI contract tests**

Assert that the rates page exposes the switch and sends the flag, and orders use `rateText` instead of raw `rate`.

- [ ] **Step 2: Run tests and verify RED**

Run: `npm test -- --run tests/unit/pages/RatesPage.spec.ts tests/unit/pages/RatesPage.formatting.spec.ts tests/unit/pages/OrdersPage.rate-display.spec.ts`

Expected: FAIL because no toggle or order presentation field exists.

- [ ] **Step 3: Implement the toggle and order formatting**

Add an accessible Quasar toggle with optimistic blocking during PATCH, update the returned row, and render backend `rateText` in both table layouts.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `npm test -- --run tests/unit/pages/RatesPage.spec.ts tests/unit/pages/RatesPage.formatting.spec.ts tests/unit/pages/OrdersPage.rate-display.spec.ts`

Expected: PASS.

### Task 5: Full verification

**Files:**
- Verify all modified files in `antex_be`, `antex_twa`, and `antex_adm`.

- [ ] **Step 1: Run backend format, lint, and full tests**

Run: `uv run ruff format --check app tests alembic && uv run ruff check app tests alembic && uv run pytest -q`

Expected: all checks pass.

- [ ] **Step 2: Run Mini App lint, tests, and production build**

Run: `npm run lint && npm test -- --run && npm run build`

Expected: all checks pass.

- [ ] **Step 3: Run admin lint, tests, and production build**

Run: `npm run lint && npm test -- --run && npm run build`

Expected: all checks pass.

- [ ] **Step 4: Review diffs and migration rollback**

Confirm calculation fields remain direct, presentation fields are isolated, only intended files changed, and Alembic downgrade removes the new columns cleanly.
