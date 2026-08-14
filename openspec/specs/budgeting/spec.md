# Budgeting Specification

## Purpose
Provide simplified YNAB-style monthly envelopes with explicit funding, activity,
rollover, and currency boundaries for each plan.

## Scope
Ready to Assign, Assigned, Activity, Available, rollover, overspending, and targets.

## Business rules
Each Plan month/category MUST calculate Ready to Assign, Assigned, Activity, Available, and rollover in its budget currency. Credit-card purchases are expenses; a card payment is a transfer. No YNAB card-payment automation is provided. Targets MAY be target-balance, monthly-funding, or due-date.

## Data model
Budget month, category envelope, assignments, activity, rollover, and target.

## Constraints
Unconverted amounts MUST be excluded or explicitly labeled, never silently converted.

## Non-goals
Multi-currency silent budget aggregation is a non-goal.
## Requirements
### Requirement: Deterministic envelopes
The system MUST calculate available funds from rollover, assignments, and applicable activity.

#### Scenario: Unconverted activity
GIVEN activity without an authorized quote to the budget currency
WHEN a budget total is shown
THEN it MUST be explicit as unconverted or excluded.

### Requirement: Plan-local monthly budget baseline
Each Plan MUST have an IANA `budget_timezone` used exclusively to determine
budget-month membership. The `003_ledger_core` migration MUST set
`America/La_Paz` as the explicit initial timezone for existing Plans. New Plan
creation MUST require an IANA timezone and MUST NOT infer it from the server.
The timezone MUST be immutable after Plan creation so historical month
membership remains deterministic.

A budget month is a `YYYY-MM` local-calendar interval beginning at that month's
start in the Plan timezone and ending at the next month's start in the same
timezone. A timezone-aware movement belongs to exactly one such interval. The
server host timezone MUST NOT affect that calculation.

#### Scenario: Classify a boundary timestamp in the Plan timezone
- **GIVEN** a Plan with an IANA timezone and a posted movement near a local month boundary
- **WHEN** the monthly summary is calculated
- **THEN** the movement belongs to the month containing its instant in the Plan timezone, independent of the server timezone.

### Requirement: Exact immutable monthly assignments
The system MUST persist each monthly assignment as an immutable,
client-UUID-idempotent record owned by one Plan and one same-Plan Category. An
assignment MUST contain a `YYYY-MM` month key, a signed exact decimal amount,
currency equal to the Plan budget currency, provenance, timestamps, and an
immutable creation fingerprint. Assignment amounts MAY be positive or negative.
Money MUST be supplied and returned as exact decimal strings; floats MUST be
rejected. Repeating the same UUID and canonical payload MUST return `200` after
the first `201`; reusing it with a different canonical payload MUST return
`409` without mutation. Changes to intended funding MUST be represented by a
new compensating or additional assignment, never update or delete an existing
record.

Assignment UUID handling MUST be safe under concurrent PostgreSQL requests.
Concurrent identical requests MUST produce one durable assignment and one `201`
plus one `200`; concurrent different payloads with the same UUID MUST produce
one `201` plus one `409`, never `500` or a partial assignment.

#### Scenario: Reverse part of an assignment
- **GIVEN** a Category has a `100.00` assignment in a budget month
- **WHEN** a client creates a separate `-25.00` exact assignment for the same Category and month
- **THEN** both assignment records remain auditable and the Category's Assigned value is `75.00`.

### Requirement: Baseline monthly summary and Category envelopes
Monthly summary and Category envelope equations MUST select only posted
`income` and `expense` movements of the required classification. Transfer
movements, including same-currency, cross-currency, and reversal legs, MUST
contribute to none of Ready to Assign, Assigned, Activity, Available, total
activity, or Category activity regardless of their effective month. No selector
MAY implement "not income means expense"; it MUST explicitly match `expense`
when calculating expense activity and explicitly match `income` when calculating
income.

#### Scenario: Calculate a baseline envelope
- **GIVEN** budget-currency income of `100.00`, a `60.00` assignment to one Category, and a posted `20.00` expense in that Category during one Plan month
- **WHEN** the monthly summary and Category envelope are requested
- **THEN** Ready to Assign is `40.00`, Assigned is `60.00`, Activity is `-20.00`, and Available is `40.00`.

#### Scenario: Exclude a same-currency transfer from envelopes
- **GIVEN** a budget-currency Transfer between two Accounts during a Plan month
- **WHEN** that month summary and every Category envelope are requested
- **THEN** neither leg contributes to Ready to Assign, Activity, Available, or any Category total.

### Requirement: Explicit unconverted budget reporting
`unconverted_by_currency` MUST contain only applicable income or expense
movements excluded because their Account currency differs from the Plan budget
currency. Transfer and reversal movements MUST never appear in
`unconverted_by_currency`, even when their currencies differ from the Plan
budget currency. In particular, `_unconverted_summary` MUST classify an amount
as expense only when `transaction_type = 'expense'`; it MUST not use an `else`
branch for every non-income classifier. SQL MUST reject a movement classifier
that does not equal its referenced Transaction type before a projection can
observe it.

#### Scenario: Exclude foreign-currency activity
- **GIVEN** a BOB-budget Plan with a posted USDT expense in a Category
- **WHEN** the month summary and that Category envelope are read
- **THEN** the USDT movement changes only its USDT Account balance, is excluded from budget totals, and appears explicitly as unconverted USDT activity.

#### Scenario: Exclude a cross-currency transfer from unconverted reporting
- **GIVEN** a BOB-budget Plan posts a BOB-to-USDT Transfer
- **WHEN** its monthly summary and Category envelopes are read
- **THEN** the Transfer changes both Account balances but creates no BOB or USDT unconverted budget entry.

#### Scenario: Explicit classifier selection excludes a foreign transfer
- **GIVEN** a BOB-budget Plan contains a valid USDT expense and a BOB-to-USDT Transfer in the same month
- **WHEN** `_unconverted_summary` and all monthly/category selectors run
- **THEN** only the expense appears as unconverted expense activity, neither transfer leg appears, and a direct-SQL classifier mismatch is rejected before either selector can run.

### Requirement: Concrete Plan-scoped budget API and minimal UI
The server MUST expose `PUT /plans/{plan_id}/budget-assignments/{assignment_id}`,
`GET /plans/{plan_id}/budget/months/{month}`,
`GET /plans/{plan_id}/budget/months/{month}/categories`, and
`GET /plans/{plan_id}/budget/months/{month}/categories/{category_id}`. The
monthly summary route MUST return Ready to Assign and its explicit unconverted
reporting; Category routes MUST return Assigned, Activity, Available, and their
explicit unconverted reporting. No endpoint for rollover, overspending policy,
Goals, Targets, Credit Card automation, or currency conversion MAY be added.

The minimal UI MUST create exact monthly assignments and show the monthly
Ready to Assign value plus Category Assigned, Activity, and Available values.
It MUST clearly display unconverted amounts by currency and MUST NOT imply a
conversion, rollover, goal, target, transfer, or reconciliation workflow.

#### Scenario: Show unconverted values in the monthly UI
- **GIVEN** the monthly API response contains unconverted USDT activity
- **WHEN** the user views the basic monthly budget screen
- **THEN** the UI labels the USDT amount as unconverted and does not include it in BOB totals.

## Acceptance criteria
Monthly envelope values, rollover, overspending, and all three target types are represented.
