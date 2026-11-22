## Why

Add a safe watcher for Binance Card notices without misclassifying reported USD as USDT.

## What Changes

User approved the initial review-only scope on 2026-10-08 after sample review.
Parse the exact observed successful USD notice contract, preserve reported
amount/currency and provenance, and persist candidates for inspection in Gmail.
Backfill already-ingested evidence and process new messages idempotently. Unknown
Card templates or malformed success notices require review without financial
facts being invented; failed transactions never become expenses.

There is no posting, settlement resolution, account mapping, FX quote, or approval
action in this scope. USD remains USD; no generic rule may equate it to USDT.

## Capabilities

### New Capabilities

- `specs/watchers/spec.md`
- `specs/exchange-rates/spec.md`

### Modified Capabilities

- None.

## Impact

Depends on Gmail evidence, not account mappings. Add PostgreSQL review storage,
a bounded worker backfill, plan-scoped read API and review display. Preserve
existing Gmail evidence, OAuth scope, financial behavior and editorial UI.

Refunds, reversals, alternate currencies, template variants, authoritative USDT
settlement evidence, and financial posting are explicitly deferred, not claimed
as implemented. They still **REQUIRE REAL SAMPLES** and separately approved work.
