# Tasks

## 1. Budget engine

- [x] 1.1 Correct continuity, future funding, signed availability and cash-first overspending; verify multi-month and correction regressions on disposable PostgreSQL.
- [x] 1.2 Add protected card payment categories and derived reserves; verify migration, funded/unfunded purchases, payments, reversals and foreign currency boundaries.
- [x] 1.3 Add atomic idempotent funding/move actions and correct target shortfalls; verify retries, conflicts, concurrent moves, insufficient funds and no ledger mutation.

## 2. Workspace

- [x] 2.1 Implement dedicated responsive budget, grouped rows, account navigation, filters and inspector with funding/move/target controls; verify frontend behavior tests and production build.
- [x] 2.2 Verify synthetic desktop/mobile flows with Playwright, retain no reference-account data in the repository, document results and run full regression/OpenSpec checks.

## 3. Shared workspace follow-up — 2026-10-21

- [x] 3.1 Share persistent navigation, account sidebar and page hierarchy across Budget, All activity, Accounts and Gmail; remove the duplicate legacy budget from activity and verify cross-route identity/navigation plus existing client workflows.
- [x] 3.2 Verify desktop/mobile routes, 200% text, keyboard and loading/error continuity with read-only synthetic browser data; record screenshots, frontend suite and build results.
