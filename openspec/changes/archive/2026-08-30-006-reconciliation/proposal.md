## Why

Provide a safe balance comparison without inventing accounting.

## What Changes

Add a side-effect-free, timestamped preview and an explicit, idempotent
confirmation identified by a client UUID. Confirmation retains an immutable
reconciliation session and, only for a non-zero discrepancy allowed by policy,
posts one protected categoryless adjustment atomically.

The server uses the Account's immutable currency and scale, derives the balance
as of a UTC statement timestamp, and applies a server-configured `block|warn`
policy with an exact tolerance expressed in Account-currency atomic units.

## Capabilities

### New Capabilities

- `specs/reconciliation/spec.md`

### Modified Capabilities

- None.

## Impact

Depends on `005-budget-engine`, derived Account balances, and posted ledger
movements. It adds revision `006_reconciliation`, Plan-scoped backend and web
flows, and changes the internal Transaction/movement classifier checks to admit
protected `reconciliation_adjustment` records while excluding them from budget
activity.
