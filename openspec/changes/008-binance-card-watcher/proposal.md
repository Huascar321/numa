## Why

Add a safe watcher for Binance Card notices without misclassifying reported USD as USDT.

## What Changes

Parse the exact sender/subject contract, preserve reported amount/currency, and
quarantine unresolved settlement asset mappings. Settlement may be resolved only
with authoritative account mapping or settlement evidence plus explicit
deterministic configuration or review; a generic rule cannot equate reported USD
to USDT.

## Capabilities

### New Capabilities

- `specs/watchers/spec.md`
- `specs/exchange-rates/spec.md`

### Modified Capabilities

- None.

## Impact

Depends on Gmail and account mappings. The observed success-template sender,
subject, MIME encoding, body fields, and timestamp semantics are resolved.
Refunds, reversals, alternate currencies, template variants, and authoritative
USDT settlement evidence **REQUIRES REAL SAMPLE**.
