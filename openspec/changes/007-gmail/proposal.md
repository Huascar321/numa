## Why

Ingest Gmail transaction notices without making push delivery a reliability dependency.

## What Changes

Add server OAuth, readonly scope, encrypted refresh tokens, full sync, History polling, cursor recovery, and idempotent ingestion.

## Capabilities

### New Capabilities

- `specs/watchers/spec.md`

### Modified Capabilities

- None.

## Impact

Depends on foundation and accounts; parser/rules/matching remain staged.
