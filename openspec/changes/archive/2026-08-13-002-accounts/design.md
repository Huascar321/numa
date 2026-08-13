# Design

## Context

`001-foundation` established the FastAPI monolith, PostgreSQL/Alembic boundary,
exact money primitive, readiness checks, and React/Vite scaffold. This change
adds only the Plan, currency, and Account registry needed by later ledger work.
There are no posted movements in this phase, so the account-balance projection
has an explicitly empty input set.

## Goals

- Persist an internal, extensible currency registry seeded with BOB and USDT.
- Persist independent Plans and Accounts with database-enforced ownership,
  allowed types, currencies, and lifecycle states.
- Provide idempotent, Plan-scoped API contracts using client-generated UUIDs.
- Expose exact derived zero balances without storing editable balances or
  opening balances.
- Add a functional minimal UI for Plan selection and Account management.
- Upgrade readiness and migration verification from `001_foundation` to
  `002_accounts`.

## Non-Goals

- Transactions, posted movements, opening balances, Categories, Pending,
  budgets, transfers, reconciliation, imports, authentication, and FX are not
  implemented here.
- Currency administration is not exposed publicly. Additional currencies need
  a later accepted migration or internal deployment change.
- Final navigation, advanced visual design, offline/PWA behavior, and polish
  remain in later changes.

## Decisions

### Migration and schema

Alembic revision `002_accounts` has `001_foundation` as its parent and becomes
the expected readiness head. A clean database reaches it through `alembic
upgrade head`, while a database already at `001_foundation` applies only the new
revision. Re-running `upgrade head` at `002_accounts` is a no-op.

The revision creates:

- `currencies`: stable `code` primary key and `decimal_places` integer. It seeds
  BOB with 2 decimals and USDT with 6. Decimal places are non-negative. There is
  no public create, update, or delete currency endpoint.
- `plans`: UUID primary key, non-empty `name`, `reporting_currency_code` foreign
  key to `currencies`, immutable `creation_fingerprint`, and timezone-aware
  `created_at`/`updated_at` timestamps. One reporting currency is also the
  Plan's budget currency in this phase.
- `accounts`: UUID primary key, required `plan_id` foreign key to `plans`,
  non-empty `name`, exact `account_type`, `currency_code` foreign key to
  `currencies`, `status`, immutable `creation_fingerprint`, and timezone-aware
  timestamps.

Account types are exactly `Bank`, `Cash`, `Wallet`, `Credit Card`, `Crypto`, and
`Other`. Status is exactly `active` or `archived`. Check constraints enforce
type/status, foreign keys enforce registered currency and required Plan
ownership, and destructive parent deletion is restricted. Indexes support
Plan-scoped Account listing and status lookup.

Neither `plans` nor `accounts` contains `balance`, `opening_balance`, or another
editable monetary accumulator. No DELETE endpoint or destructive service is
introduced.

### Durable creation idempotency

The client chooses each Plan or Account UUID and sends it in the PUT path. The
server computes a deterministic fingerprint from the canonical creation
identity and payload and stores it with the resource. This immutable fingerprint
is distinct from mutable names, so a replay remains recognizable after a later
rename.

- A first valid PUT returns the created resource.
- The same UUID and canonical creation payload returns the existing current
  resource without creating a duplicate.
- The same UUID with a different canonical creation payload returns conflict and
  leaves the original resource unchanged.

For an Account, the creation identity includes its Plan ID and the creation
payload includes name, type, and currency. For a Plan, it includes name and
reporting currency. Fingerprints are server-derived and are never accepted from
clients or exposed as mutable fields.

### Plan and Account invariants

Every Account belongs to exactly one Plan. All nested Account reads and
mutations query by both `plan_id` and `account_id`; an Account belonging to a
different Plan is not returned or mutated and yields the same not-found response
as an unknown Account.

Account Plan, type, and currency are immutable after creation. Rename accepts
only a new name. Archive is a one-way `active` to `archived` transition; a
repeated archive request returns the same archived resource. Archived Accounts
remain listable/readable but reject rename and all future operational mutations.
Later posting services must reuse this active-account guard. There is no
unarchive or delete operation in this change.

Only currencies already present in `currencies` may be selected. The system
does not create a missing currency, infer one from a name/type, convert values,
or aggregate unlike currencies.

### Exact derived balance

Before `003-ledger-core`, the set of posted movements is empty by definition.
The Account read model derives `Decimal(0)` from that empty set and formats it to
the currency's declared scale: BOB is `"0.00"` and USDT is `"0.000000"`.
Responses use `{ "amount": "...", "currency": "..." }`; monetary values are
JSON strings and never JSON floating-point numbers. Create and patch schemas do
not accept `balance` or `opening_balance`.

### HTTP API

The authoritative FastAPI monolith exposes only these endpoints in this phase:

- `GET /currencies` — list registered currencies as `code` and
  `decimal_places`.
- `PUT /plans/{plan_id}` — idempotently create a Plan from `name` and
  `reporting_currency_code`.
- `GET /plans` — list Plans.
- `GET /plans/{plan_id}` — read one Plan.
- `PATCH /plans/{plan_id}` — rename one Plan; the body contains only `name`.
- `PUT /plans/{plan_id}/accounts/{account_id}` — idempotently create an active
  Account from `name`, `account_type`, and `currency_code`.
- `GET /plans/{plan_id}/accounts` — list active and archived Accounts in that
  Plan.
- `GET /plans/{plan_id}/accounts/{account_id}` — read one scoped Account.
- `PATCH /plans/{plan_id}/accounts/{account_id}` — rename an active Account; the
  body contains only `name`.
- `POST /plans/{plan_id}/accounts/{account_id}/archive` — archive an Account
  idempotently.

Create responses distinguish first creation from replay, and payload conflicts
return HTTP 409. Unknown currencies, types, or invalid input are rejected.
Cross-Plan nested access returns 404 without disclosing the other Plan. Archived
mutation returns 409. No route accepts balance fields, performs conversion, or
uses DELETE.

### Minimal client flow

The web application adds React Router and TanStack Query. Minimal routes are
`/plans` for Plan creation/selection and `/plans/:planId/accounts` for Account
management. Query data comes from the server and mutations invalidate/refetch
the relevant authoritative queries.

The UI can create and select a Plan, then list, create, rename, and archive its
Accounts. Each Account displays exact type, currency, lifecycle state, and the
derived zero balance string. Archived Accounts remain visible and cannot expose
rename/archive-as-new-operation controls. This phase does not implement final
navigation, advanced styling, or PWA polish.

## Verification Strategy

- Apply `alembic upgrade head` to a completely empty PostgreSQL 18 database and
  prove both `001_foundation` and `002_accounts` are recorded in sequence.
- Start from a PostgreSQL database explicitly at `001_foundation`, upgrade to
  head, and prove a second upgrade is safe.
- Inspect tables, seeds, constraints, foreign keys, indexes, absence of balance
  columns, and readiness at `002_accounts`.
- Test creation replay/conflict, immutable fields, archive behavior, no DELETE,
  cross-Plan isolation, registered-currency enforcement, and exact string zero
  balances for both initial currencies.
- Exercise all API paths and minimal Plan/Account UI flows, run the web build,
  and run strict OpenSpec validation.
