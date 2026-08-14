# Accounts delta

## MODIFIED Requirements

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
