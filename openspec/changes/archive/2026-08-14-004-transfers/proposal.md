## Why

Prevent movement between accounts from becoming false income or expense.

## What Changes

Add Plan-scoped, idempotent Transfer roots with exactly two immutable linked
Transaction legs and their posted Account movements. A Transfer posts an
outbound leg and an inbound leg together, supports same- and cross-currency
evidence, and can only be financially changed through an idempotent,
non-destructive reversal that appends a compensating Transfer pair.

The change adds the `004_transfers` migration after `003_ledger_core`, a
Transfer API and minimal UI, and projection rules that change Account balances
without treating transfers as income, expense, category activity, budget
activity, unconverted activity, or analytics activity.

## Capabilities

### New Capabilities

- `specs/transfers/spec.md`

### Modified Capabilities

- `specs/accounts/spec.md`
- `specs/transactions/spec.md`
- `specs/budgeting/spec.md`
- `specs/analytics/spec.md`

## Impact

Depends on Accounts and `003_ledger_core`. It evolves the ledger's
income-or-expense-only type/category checks so internally-created `transfer`
Transaction legs can remain canonical, immutable, and categoryless while each
still owns exactly one original posted movement. It changes Account balance and
Plan activity projections, budget filtering, and the analytics reporting
boundary. It does not execute an exchange, silently convert currency, create or
consume a Quote, reconcile a statement, or permit destructive financial edits.
