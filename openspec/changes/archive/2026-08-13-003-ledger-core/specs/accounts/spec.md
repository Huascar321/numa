# Accounts delta

## MODIFIED Requirements

### Requirement: Derived account balance
Account balance MUST be derived exclusively from the exact signed sum of posted
Account movements belonging to that Account. The projection MUST include the
original, compensating, and replacement movements created by Transaction
corrections. It MUST NOT be stored, editable, cached as an authoritative
accumulator, or inferred from Transaction current-state fields. Monetary API
values MUST be decimal strings at the Account currency's declared scale and
MUST never be JSON floats. Create and update requests MUST reject `balance` and
`opening_balance` fields.

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

## ADDED Requirements

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
balances. Every ledger posting and correction replacement that would select an
archived Account MUST be rejected. A correction that preserves an already
historical archived Account snapshot remains readable through its existing
movements but MUST NOT reactivate or mutate the Account.

#### Scenario: Correct to an archived replacement Account
- **GIVEN** a Transaction is posted to an active Account and a different Account in the same Plan is archived
- **WHEN** a correction attempts to move the Transaction to the archived Account
- **THEN** the correction is rejected and no compensating or replacement movement is committed.

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
After a successful Transaction posting or correction, the client MUST refetch
the Plan's Transactions and Accounts, including every affected Account balance.
It MUST also refetch the affected monthly summary and Category envelope queries;
it MUST NOT derive a local balance or budget result from the request payload.

#### Scenario: Refresh projections after a correction
- **GIVEN** a visible Transaction whose correction changes its Account, Category, or local month
- **WHEN** the correction succeeds
- **THEN** the client displays the server-authoritative Transaction, every affected Account balance, and the new monthly/category projections.
