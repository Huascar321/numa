# Accounts delta

## ADDED Requirements

### Requirement: Migration-owned currency, Plan, and Account persistence
Alembic revision `002_accounts` MUST follow `001_foundation` and MUST create
`currencies`, `plans`, and `accounts`. `currencies` MUST initially contain BOB
with 2 decimal places and USDT with 6 decimal places. The registry MUST remain
extensible through accepted internal schema changes, but this change MUST expose
no public currency administration API.

`plans` MUST persist a client-generated UUID, name, one budget/reporting
currency, immutable creation fingerprint, and timestamps. `accounts` MUST
persist a client-generated UUID, exactly one Plan, name, type, currency, status,
immutable creation fingerprint, and timestamps. Account type MUST be exactly
`Bank`, `Cash`, `Wallet`, `Credit Card`, `Crypto`, or `Other`; status MUST be
exactly `active` or `archived`. Database constraints MUST enforce allowed type,
allowed status, registered currencies, and required Plan ownership. No table in
this change MAY contain editable balance or opening-balance columns.

#### Scenario: Upgrade a clean database
- **GIVEN** an empty PostgreSQL 18 database
- **WHEN** `alembic upgrade head` is run
- **THEN** revisions `001_foundation` and `002_accounts` are applied in order, the initial currencies and constrained Plan/Account schema exist, and readiness reports available at `002_accounts`.

#### Scenario: Upgrade from foundation
- **GIVEN** a PostgreSQL 18 database at revision `001_foundation`
- **WHEN** it is upgraded to head twice
- **THEN** `002_accounts` is applied once, the second upgrade is a no-op, and the resulting schema and revision remain unchanged.

### Requirement: Plan ownership and immutable Account identity
Every Account MUST belong to exactly one Plan. Account Plan, type, and currency
MUST be immutable after creation. Nested Account queries and mutations MUST
scope by both Plan UUID and Account UUID so that an Account from another Plan is
neither returned nor modified. Unknown currency codes MUST be rejected; the
system MUST NOT silently add, infer, convert, or aggregate currencies.

#### Scenario: Create account
- **GIVEN** an existing Plan and registered currency
- **WHEN** an Account is created with one of the six exact types
- **THEN** it is stored as `active` in exactly that Plan with its requested immutable type and currency.

#### Scenario: Cross-Plan nested access
- **GIVEN** an Account belongs to Plan A
- **WHEN** it is read, renamed, or archived through Plan B
- **THEN** the request returns not found and no Account data or state is changed.

#### Scenario: Attempt to change Account identity
- **GIVEN** an existing Account
- **WHEN** an update attempts to change its Plan, type, or currency
- **THEN** the request is rejected and the persisted Account remains unchanged.

### Requirement: Non-destructive Account lifecycle
Archiving MUST be a one-way, non-destructive lifecycle operation. An archived
Account MUST remain listable and readable for historical use and MUST reject
rename and future operational mutations. Repeating the archive operation MUST
return the same archived resource without another state transition. The system
MUST provide no Account or Plan deletion endpoint.

#### Scenario: Archive an Account
- **GIVEN** an active Account
- **WHEN** it is archived
- **THEN** its status becomes `archived`, its identity and historical readability are retained, and later mutation is blocked.

#### Scenario: Repeat Account archive
- **GIVEN** an archived Account
- **WHEN** the archive operation is repeated
- **THEN** the same archived Account is returned without destructive or duplicate effects.

### Requirement: Derived account balance
Account balance MUST be derived and MUST NOT be stored or editable. Before
`003-ledger-core`, the posted-movement set is empty, so every Account MUST expose
exact zero in its own registered currency. Monetary API values MUST be decimal
strings at the currency's declared scale and MUST never be JSON floats. Create
and update requests MUST reject `balance` and `opening_balance` fields.

#### Scenario: Read initial exact balances
- **GIVEN** one BOB Account and one USDT Account before ledger movements exist
- **WHEN** they are read
- **THEN** their balances are respectively `{ "amount": "0.00", "currency": "BOB" }` and `{ "amount": "0.000000", "currency": "USDT" }`.

#### Scenario: Attempt to set an opening balance
- **GIVEN** a Plan exists
- **WHEN** Account creation or update includes `balance` or `opening_balance`
- **THEN** the request is rejected and no monetary accumulator is persisted.

### Requirement: Client-UUID idempotent creation
Plan and Account creation MUST use client-generated UUIDs in the resource path.
The server MUST retain a deterministic fingerprint of each canonical creation
request. Repeating the same UUID and canonical creation payload MUST return the
existing current resource without duplication, including after a rename.
Repeating the UUID with a different creation payload MUST return conflict and
MUST NOT change the original resource.

#### Scenario: Replay Plan creation after rename
- **GIVEN** a Plan was created from a client UUID and payload and was later renamed
- **WHEN** the original creation request is replayed
- **THEN** the current renamed Plan is returned and no second Plan is created.

#### Scenario: Reuse Account UUID with different payload
- **GIVEN** an Account UUID is bound to a canonical creation payload
- **WHEN** the UUID is submitted with a different name, type, currency, or Plan identity
- **THEN** the request returns conflict and the original Account remains unchanged.

### Requirement: Concrete Plan and Account HTTP API
The server MUST expose `GET /currencies`; `PUT /plans/{plan_id}`, `GET /plans`,
`GET /plans/{plan_id}`, and `PATCH /plans/{plan_id}`; plus
`PUT /plans/{plan_id}/accounts/{account_id}`,
`GET /plans/{plan_id}/accounts`,
`GET /plans/{plan_id}/accounts/{account_id}`,
`PATCH /plans/{plan_id}/accounts/{account_id}`, and
`POST /plans/{plan_id}/accounts/{account_id}/archive`. Plan PATCH and Account
PATCH MUST accept name only. No DELETE endpoint MAY be added.

#### Scenario: Rename a Plan and active Account
- **GIVEN** a Plan with an active Account
- **WHEN** each rename endpoint receives a valid name-only payload
- **THEN** only the requested name and update timestamp change, while reporting currency, Plan ownership, Account type, currency, and status remain unchanged.

#### Scenario: Unsupported destructive route
- **GIVEN** a Plan or Account exists
- **WHEN** a client attempts an HTTP DELETE for it
- **THEN** no DELETE route exists and the resource remains unchanged.

### Requirement: Minimal authoritative Accounts UI
The React client MUST introduce React Router and TanStack Query with a functional
Plan creation/selection flow and a Plan-scoped Account flow. It MUST list,
create, rename, and archive Accounts and display type, currency, status, and
derived zero balance from server responses. This change MUST NOT implement final
navigation, advanced visual design, or PWA polish.

#### Scenario: Manage Accounts in a selected Plan
- **GIVEN** a user creates or selects a Plan
- **WHEN** the user opens that Plan's Account view
- **THEN** the UI uses authoritative query data to create, list, rename, and archive scoped Accounts and displays each exact zero balance without client-side financial state.

### Requirement: Deferred financial capabilities
This change MUST NOT implement transactions, posted movements, opening balances,
Categories, Pending, budgets, transfers, reconciliation, imports,
authentication, or FX behavior.

#### Scenario: Accounts phase remains pre-ledger
- **GIVEN** the Accounts phase is implemented
- **WHEN** its schema, API, and UI are inspected
- **THEN** only currencies, Plans, Accounts, lifecycle, and empty-set derived balances exist, with later financial capabilities absent.
