# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- ATXG wallet model (`AexWallet`) for storing user ATXG balances
- ATXG ledger entry model (`AexLedgerEntry`) for tracking ATXG transactions (accrual, spend, conversion)
- ATXG referral rate model (`AexReferralRate`) for configurable ATXG conversion rates
- User model field `referral_code` — unique 8-character referral code per user
- `ReferralService` — referral code generation, referral link resolution, ATXG bonus accrual for referrer and referred user
- `AexService` — wallet balance operations, ledger entry management, ATXG-to-currency conversion
- `AexRateService` — CRUD for ATXG conversion rates
- Referral API endpoints: `GET /api/referral/info`, `POST /api/referral/apply`
- ATXG API endpoints: `GET /api/aex/wallet`, `GET /api/aex/ledger`, `POST /api/aex/convert`
- Admin ATXG API: `GET/POST /api/admin/aex/rates`, `GET /api/admin/aex/wallets`, `GET /api/admin/aex/journal`, `POST /api/admin/aex/manual-op`, `POST /api/admin/aex/generate-referral-codes`
- Alembic migration `014_add_aex_referral` — creates `aex_wallets`, `aex_ledger_entries`, `aex_referral_rates` tables and adds `referral_code` column to users
- Batch referral code generation endpoint — generates unique codes for all users with `referral_code IS NULL`
- Unit tests for ATXG models, ATXG service, ATXG rate service, referral service, ATXG API, admin ATXG API

### Changed

- Order flow and order status services updated to trigger ATXG accrual on completed orders
- Broadcast audience module updated to support referral-related queries
- Telegram start handler updated to process referral deep-links
