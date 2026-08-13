# Tasks

## 1. PostgreSQL schema and migration chain

- [x] 1.1 Add Alembic revision `002_accounts` after `001_foundation`; create `currencies`, `plans`, and `accounts`, seed BOB/2 and USDT/6, and add exact type/status checks, currency/Plan foreign keys, restrictive lifecycle constraints, Plan-scoped indexes, timestamps, and immutable creation fingerprints without balance or opening-balance columns.
- [x] 1.2 Update the application models and database metadata for Currency, Plan, and Account while preserving the single PostgreSQL session boundary and exact non-float types.
- [x] 1.3 Update readiness to require `002_accounts`; add PostgreSQL 18 migration tests for an empty database, a database at `001_foundation`, a repeated `upgrade head`, expected seeds/schema/constraints/indexes, and absence of stored balance fields.

## 2. Domain contracts and services

- [x] 2.1 Define typed Currency, Plan, Account, account-type, account-status, create, rename, archive, and response contracts; restrict types to Bank, Cash, Wallet, Credit Card, Crypto, and Other and statuses to `active|archived`.
- [x] 2.2 Implement the currency read service with BOB and USDT scale metadata, registered-currency validation, and no public currency mutation or silent currency creation/conversion.
- [x] 2.3 Implement idempotent Plan creation from a client UUID and canonical creation fingerprint, plus list/get/rename behavior; prove matching replay returns the current resource and conflicting replay returns conflict without mutation.
- [x] 2.4 Implement Plan-scoped Account create/list/get/rename/archive services with client-UUID idempotency, immutable Plan/type/currency, one-way non-destructive archive, active-account mutation guard, and no delete operation.
- [x] 2.5 Implement nested Plan isolation by querying Account mutations and reads with both Plan UUID and Account UUID; prove cross-Plan access returns not found and does not disclose or mutate the Account.
- [x] 2.6 Implement the pre-ledger balance projection as exact zero from an empty movement set and serialize monetary responses at currency scale as decimal strings; reject JSON floats and all balance/opening-balance inputs.

## 3. FastAPI endpoints

- [x] 3.1 Add `GET /currencies` and Plan endpoints `PUT /plans/{plan_id}`, `GET /plans`, `GET /plans/{plan_id}`, and name-only `PATCH /plans/{plan_id}` with documented create/replay/conflict responses.
- [x] 3.2 Add Account endpoints `PUT /plans/{plan_id}/accounts/{account_id}`, `GET /plans/{plan_id}/accounts`, `GET /plans/{plan_id}/accounts/{account_id}`, name-only `PATCH /plans/{plan_id}/accounts/{account_id}`, and `POST /plans/{plan_id}/accounts/{account_id}/archive`.
- [x] 3.3 Add API integration tests for all success/error paths, client-UUID replay and conflict, unknown currencies/types, immutable fields, archived mutation, repeated archive, cross-Plan isolation, exact string balances, rejected balance inputs, and absence of Plan/Account/currency DELETE or currency-admin routes.

## 4. Minimal React client

- [x] 4.1 Add React Router and TanStack Query dependencies and providers, with minimal routes `/plans` and `/plans/:planId/accounts` and server responses as authoritative state.
- [x] 4.2 Implement the functional Plan screen for listing, creating with a client UUID, selecting, consulting, and renaming Plans with registered reporting-currency selection.
- [x] 4.3 Implement the Plan-scoped Account screen for listing, consulting, creating, renaming, and archiving Accounts; display exact type, currency, `active|archived` status, and server-provided zero balance, while disabling archived mutations.
- [x] 4.4 Add focused client tests for Plan selection and Account create/rename/archive flows, query invalidation/refetch, exact balance display, archived controls, and absence of final navigation/PWA behavior.

## 5. Verification and scope guard

- [x] 5.1 Run API unit tests and the complete PostgreSQL 18 migration/service/API suite from both required database starting points; verify idempotency, Plan isolation, archive rules, immutable identity, exact-money string serialization, readiness, and no financial tables or balance columns.
- [x] 5.2 Run the client tests and production build, then run `openspec validate 002-accounts --strict --no-interactive` and `openspec validate --all --strict --no-interactive`; mark tasks complete only after their corresponding implementation and checks pass.
- [x] 5.3 Confirm the implementation contains no transactions, posted movements, opening balances, Categories, Pending, budgets, transfers, reconciliation, imports, authentication, FX, public currency administration, DELETE endpoints, final navigation, advanced visual design, or PWA polish.
