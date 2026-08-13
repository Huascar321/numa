## Why

Create the first implementable, auditable ledger and a deliberately limited
monthly budgeting baseline. Accounts can no longer report only the empty-set
balance once this phase posts movements.

## What Changes

Add migration `003_ledger_core` after `002_accounts`; Plan budget time zones;
Category Groups, Categories, protected `Pendientes`, Tags, Transactions,
posted account movements, immutable correction history, Transaction--Tag
relations, and idempotent monthly budget assignments.

Expose manual income and expense posting, derived account balances,
non-destructive category and tag management, transaction correction, and the
monthly Ready to Assign / Assigned / Activity / Available baseline. All money
remains exact and all finance writes remain auditable and retry-safe.

Transfers, `cleared`, reconciliation-adjustment creation, rollover,
overspending policy, goals, targets, and credit-card budgeting automation are
explicitly deferred to their ordered changes.

## Capabilities

### New Capabilities

- `specs/transactions/spec.md`
- `specs/budgeting/spec.md`

### Modified Capabilities

- `specs/accounts/spec.md`

## Impact

Depends on `002_accounts`. It changes Account balance projection from the
pre-ledger empty set to the exclusive sum of posted movements, and extends
Plans with an immutable IANA budget timezone and atomic `Pendientes`
provisioning. `004-transfers`, `005-budget-engine`, and
`006-reconciliation` consume this ledger boundary without being implemented
here.
