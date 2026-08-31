# Tasks

## 1. Contract and migration

- [x] 6.1 Define bounded plain `NUMERIC(38,18)` statement money, inclusive UTC as-of balance, and `statement - derived` discrepancy contracts with `block|warn` plus non-negative atomic-unit tolerance configuration.
- [x] 6.2 Add child revision `006_reconciliation` after `005_budget_engine`, immutable Plan-scoped sessions, categoryless reconciliation classifier support, one-adjustment SQL uniqueness, deferred integrity, append-only/correction guards, indexes, exact `NUMERIC`/`TIMESTAMPTZ` persistence, and update `EXPECTED_REVISION`.
- [x] 6.3 Verify clean and `005_budget_engine` upgrades, repeated head, readiness, schema/check/FK/index contracts, no float columns, direct-SQL immutability, and one-adjustment enforcement.

## 2. Backend behavior and API

- [x] 6.4 Implement strict preview/confirmation/history schemas and validated server settings with safe `block`/zero-atom defaults.
- [x] 6.5 Implement Plan-scoped inclusive as-of calculation and truly side-effect-free preview using the Account's immutable currency and exact scale.
- [x] 6.6 Implement atomic explicit confirmation with a common deterministic Account-row lock boundary for every movement writer, zero-discrepancy audit without movement, protected categoryless adjustment, archived-Account rules, immutable history, UUID replay/conflict, and concurrent no-duplicate behavior.
- [x] 6.7 Add Plan-scoped preview, confirm, and history routes with authoritative response contracts and correct `200|201|404|409|422` behavior.
- [x] 6.8 Exclude reconciliation adjustments from budget/unconverted activity and reject generic correction while retaining their Account-balance effect and audit visibility.

## 3. Authoritative web flow

- [x] 6.9 Add typed client operations and a Plan-scoped UI for exact preview, policy/tolerance display, explicit warning acceptance and confirmation, and immutable history.
- [x] 6.10 After confirmation, invalidate/refetch authoritative reconciliation history, Accounts, Transactions, and Budget queries without applying local balance deltas.

## 4. Verification

- [x] 6.11 Add focused backend/migration tests for exact money, inclusive as-of, preview purity, zero confirmation, warning/block boundaries, archived Accounts, adjustment guards/exclusion, retry/conflict/concurrency, and Plan isolation.
- [x] 6.12 Add focused web tests for preview/confirm/history, warning acceptance, zero result, and authoritative refetch.
- [x] 6.13 Run strict OpenSpec validation, relevant/full available backend tests, web tests/build, and `git diff --check`; mark only observably completed tasks.
