## 1. Persistence and migration

- [x] 1.1 Add conversation, message, revision and attachment models with repository tests.
- [x] 1.2 Add linear Alembic revision `032` after current `dev` revision `031` and verify a single head.
- [x] 1.3 Preserve cash-rate changes while merging `origin/dev` into the feature branch.

## 2. Manager API and realtime foundation

- [x] 2.1 Add operator-only REST endpoints, one-time WebSocket tickets and USER `403` coverage.
- [x] 2.2 Add Redis Pub/Sub fan-out, heartbeat and REST reconciliation contract.
- [x] 2.3 Add manager chat/order schemas and reuse the existing order status service.

## 3. Telegram capture and delivery

- [x] 3.1 Capture unhandled private messages and edited updates with Telegram identity dedupe and revisions.
- [x] 3.2 Add inbound attachment metadata and outbound text/attachment endpoints.
- [x] 3.3 Add offline manager fallback notification and realtime events after persistence.

## 4. Durability remediation

- [x] 4.1 Propagate transient ordinary and edited Telegram capture failures for redelivery with RED/GREEN tests.
- [x] 4.2 Replace unread read-modify-write with an atomic database increment and concurrency regression test.
- [x] 4.3 Store presence/viewing per `connection_id` across backend instances and preserve other live connections on disconnect.
- [ ] 4.4 Persist new order notification message ID independently of cached write-access changes.
- [ ] 4.5 Forward reply target using the stored Telegram message ID.
- [ ] 4.6 Bulk-enrich conversation lists without per-conversation message/order queries.
- [ ] 4.7 Retain failed outbound attachment bytes for idempotent retry and add durable-storage coverage.
- [ ] 4.8 Support sticker, animation, audio and video note metadata in Telegram capture.
- [ ] 4.9 Remove personal manager Telegram URLs from operational flows without breaking FSM routing.

## 5. Verification

- [x] 5.1 Run focused RED/GREEN tests for update redelivery, concurrent unread and multi-connection Redis state.
- [x] 5.2 Run Ruff and the full backend test suite.
- [ ] 5.3 Verify migration upgrade/downgrade on a clean database and generate offline SQL.
- [ ] 5.4 Run `openspec validate --strict --all` after all remediation tasks are complete.
