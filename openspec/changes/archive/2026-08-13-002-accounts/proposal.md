## Why

The foundation now provides durable PostgreSQL persistence, exact-money
primitives, and an authoritative API boundary, but there is no implementable
workspace or account registry. The ledger phase needs stable Plan ownership,
explicit currencies, immutable account identity facts, and non-destructive
lifecycle behavior before it can post movements safely.

## What Changes

Add Alembic revision `002_accounts` with an internal currency registry, Plans,
and Plan-scoped Accounts. Expose concrete idempotent Plan and Account APIs,
enforce immutable account type/currency and archived-account behavior, update
database readiness to the new head, and provide a minimal React Router + TanStack
Query UI for selecting Plans and managing Accounts.

Until `003-ledger-core` introduces posted movements, every Account exposes an
exact derived zero balance in its own currency. This change stores no balance or
opening balance, performs no FX conversion, and adds no financial mutation.

## Capabilities

### New Capabilities

- `specs/accounts/spec.md`

### Modified Capabilities

- None.

## Impact

Depends on archived `001-foundation`. It adds PostgreSQL schema, FastAPI
models/services/routes/tests, and minimal client routing/query flows. It does
not add transactions, movements, categories, budgets, transfers,
reconciliation, imports, authentication, or FX; those remain in later ordered
changes. The resulting Plan and Account boundary is the prerequisite for
`003-ledger-core`.
