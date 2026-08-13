# Budgeting delta

## ADDED Requirements

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
For each requested Plan month, the server MUST calculate only these baseline
values in the Plan budget currency from posted movements and immutable
assignments:

- `Ready to Assign = income for the month - assignments for the month`;
- `Assigned(category) = assignments for the Category and month`;
- `Activity(category) = posted expense movement activity for the Category and month`, signed negative; and
- `Available(category) = Assigned(category) + Activity(category)`.

Income contributes to Ready to Assign but not Category Activity. Only posted
movements whose Account currency equals the Plan budget currency may contribute
to these equations. The calculation MUST include compensating and replacement
movements so Transaction corrections revise balances and activity audibly. It
MUST NOT apply rollover, an overspending policy across months, Goals, Targets,
or special Credit Card automation in this phase.

#### Scenario: Calculate a baseline envelope
- **GIVEN** budget-currency income of `100.00`, a `60.00` assignment to one Category, and a posted `20.00` expense in that Category during one Plan month
- **WHEN** the monthly summary and Category envelope are requested
- **THEN** Ready to Assign is `40.00`, Assigned is `60.00`, Activity is `-20.00`, and Available is `40.00`.

### Requirement: Explicit unconverted budget reporting
A Transaction whose Account currency differs from the Plan budget currency MUST
still affect its Account balance through its posted movement. It MUST NOT be
silently converted or included in Ready to Assign, Assigned, Activity, or
Available. The monthly summary MUST report excluded income and expense as
`unconverted_by_currency`, and each Category envelope MUST report its excluded
expense activity as `unconverted_by_currency`. Each entry MUST keep one
currency, exact decimal-string values, and the contributing Transaction or
movement identifiers; values from different currencies MUST NOT be aggregated.

#### Scenario: Exclude foreign-currency activity
- **GIVEN** a BOB-budget Plan with a posted USDT expense in a Category
- **WHEN** the month summary and that Category envelope are read
- **THEN** the USDT movement changes only its USDT Account balance, is excluded from budget totals, and appears explicitly as unconverted USDT activity.

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
