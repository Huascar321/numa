# Accounts Specification

## Purpose
Manage independent-plan account registries with currencies, lifecycle, and
derived balances that preserve plan boundaries.

## Scope
Bank, Cash, Wallet, Credit Card, Crypto, and Other accounts with extensible currencies including BOB and USDT.

## Business rules
Each account MUST belong to one Plan and have one currency. Balances MUST be derived, not entered. A Plan MUST have one reporting/budget currency and MUST NOT silently aggregate unconverted currencies.

## Data model
Account: plan, type, name, currency, lifecycle, and derived balance.

## Constraints
Archived accounts MUST retain readable history and reject new postings.

## Non-goals
Shared accounts and multi-plan accounts are non-goals.
## Requirements
### Requirement: Plan-scoped account registry
The system MUST store account type, currency, and lifecycle in its Plan.

#### Scenario: Archive historical account
GIVEN an account with posted history
WHEN it is archived
THEN history MUST remain readable and new postings MUST be blocked.

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
Account balance MUST be derived exclusively from the exact signed sum of posted
Account movements belonging to that Account. The projection MUST include the
original, compensating, and replacement movements created by Transaction
corrections, plus both Transfer legs and both reversal legs in their respective
Accounts. It MUST NOT be stored, editable, cached as an authoritative
accumulator, inferred from Transaction current-state fields, aggregated, or
converted across currencies. Monetary API values MUST be decimal strings at the
Account currency's declared scale and MUST never be JSON floats. Create and
update requests MUST reject `balance` and `opening_balance` fields. A
same-currency Transfer changes the source by its negative outbound movement and
conversion.

#### Scenario: Read initial exact balances
- **GIVEN** one BOB Account and one USDT Account before ledger movements exist
- **WHEN** they are read
- **THEN** their balances are respectively `{ "amount": "0.00", "currency": "BOB" }` and `{ "amount": "0.000000", "currency": "USDT" }`.

#### Scenario: Read a balance after posted ledger activity
- **GIVEN** an Account has posted income and expense movements in its registered currency
- **WHEN** the Account or its Plan-scoped balance endpoint is read
- **THEN** it reports the exact sum of those movements in that currency without a stored balance field.

#### Scenario: Attempt to set an opening balance
- **GIVEN** a Plan exists
- **WHEN** Account creation or update includes `balance` or `opening_balance`
- **THEN** the request is rejected and no monetary accumulator is persisted.

#### Scenario: Derive two balances from a cross-currency Transfer
- **GIVEN** a BOB Account sends `100.00` BOB to a USDT Account that receives `10.000000` USDT
- **WHEN** both Account balances are read after the Transfer commits
- **THEN** the BOB balance includes `-100.00`, the USDT balance includes `10.000000`, and neither response silently converts or aggregates the values.

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

### Requirement: Ledger-era Plan timezone and protected Category provision
The Plan persistence introduced by `002_accounts` MUST be extended by
`003_ledger_core` with a non-null IANA `budget_timezone`. Existing Plans MUST
receive the explicit initial value `America/La_Paz`. New Plan creation MUST
require an IANA timezone, preserve it as immutable Plan identity, and atomically
create exactly one active protected `Pendientes` Category in that Plan. A
failed Plan or protected-Category creation MUST leave neither partial resource
durable.

#### Scenario: Create a new Plan with its protected Category
- **GIVEN** a client submits a valid new Plan UUID, reporting currency, and IANA timezone
- **WHEN** Plan creation succeeds
- **THEN** the Plan and exactly one active protected `Pendientes` Category are committed together.

### Requirement: Archived Account posting guard after ledger activation
Archived Accounts MUST retain readable historical movements and their derived
balances. Every ledger posting, correction replacement, Transfer leg, and
reversal leg that would select an archived Account MUST be rejected. A
correction that preserves an already historical archived Account snapshot
remains readable through its existing movements but MUST NOT reactivate or
mutate the Account. The rejection MUST leave both Account balances and all
Transfer history unchanged.

#### Scenario: Correct to an archived replacement Account
- **GIVEN** a Transaction is posted to an active Account and a different Account in the same Plan is archived
- **WHEN** a correction attempts to move the Transaction to the archived Account
- **THEN** the correction is rejected and no compensating or replacement movement is committed.

#### Scenario: Reject transfer to an archived destination
- **GIVEN** an active source Account and an archived same-Plan destination Account
- **WHEN** a Transfer is requested
- **THEN** the request is rejected and neither Account receives a new movement.

### Requirement: Plan-scoped derived balance API
The server MUST expose `GET /plans/{plan_id}/accounts/{account_id}/balance` in
addition to returning the same derived balance in Account reads. The route MUST
scope by both Plan UUID and Account UUID, return not found for a cross-Plan
Account, and return the Account currency with an exact decimal-string balance.
It MUST expose no balance mutation route.

#### Scenario: Reject cross-Plan balance access
- **GIVEN** an Account belongs to Plan A
- **WHEN** its balance route is requested through Plan B
- **THEN** the request returns not found and reveals no balance or movement data.

### Requirement: Authoritative balance refresh after ledger writes
After a successful Transaction posting, correction, Transfer create, or
reversal, the client MUST refetch the Plan's grouped Transaction/activity data,
queries. It MUST NOT derive a local balance, budget, or FX conversion delta from
request data.

#### Scenario: Refresh projections after a correction
- **GIVEN** a visible Transaction whose correction changes its Account, Category, or local month
- **WHEN** the correction succeeds
- **THEN** the client displays the server-authoritative Transaction, every affected Account balance, and the new monthly/category projections.

#### Scenario: Refresh both sides after reversal
- **GIVEN** a visible Transfer between two Accounts
- **WHEN** its reversal succeeds
- **THEN** the client displays server-authoritative grouped history and refreshed balances for both Accounts plus refreshed Budget projections.

## Acceptance criteria
All six account types and derived balances are supported.
