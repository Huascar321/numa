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
The server MUST expose the existing Plan-scoped budget routes:

- `PUT /plans/{plan_id}/budget-assignments/{assignment_id}`;
- `GET /plans/{plan_id}/budget/months/{month}`;
- `GET /plans/{plan_id}/budget/months/{month}/categories`; and
- `GET /plans/{plan_id}/budget/months/{month}/categories/{category_id}`.

The monthly summary route MUST return Ready to Assign and explicit
`unconverted_by_currency` reporting. Category routes MUST return Assigned,
Activity, Available, and their explicit unconverted reporting, plus applicable
rollover, overspending outcomes, and goal status activated by this change. This
change supersedes the baseline prohibition on exposing rollover, overspending
policy, Goals, and Targets in those existing budget responses. It does not add
Credit Card payment automation, a separate payment-category workflow, or
currency conversion.

The minimal UI MUST create exact monthly assignments and show monthly Ready to
Assign plus Category Assigned, Activity, and Available values. It MAY show
rollover, overspending outcomes, and goal status, but MUST label unconverted
amounts and MUST NOT imply silent conversion, automatic payment Categories, or
automatic movement between Categories.

#### Scenario: Show unconverted values in the monthly UI
- **GIVEN** the monthly API response contains unconverted USDT activity
- **WHEN** the user views the basic monthly budget screen
- **THEN** the UI labels the USDT amount as unconverted and does not include it in BOB totals.

#### Scenario: Return applicable budget outcomes without silent conversion
- **GIVEN** a Plan-scoped budget month has applicable rollover, Cash/Bank or
  Credit Card overspending, a goal, and activity in a currency different from
  the Plan currency
- **WHEN** the monthly summary or Category route is queried
- **THEN** the response includes applicable `rollover`, overspending outcomes,
  and goal status in the Category envelope, reports the differing-currency
  activity explicitly in `unconverted_by_currency`, and does not silently
  convert it.

### Requirement: Category rollover and overspending policy
Budget months MUST carry positive Category Available forward and MUST apply a
different overspending policy by Account type. At month close, positive
Category Available MUST become the next month's Category rollover and contribute
to that month's Available. Cash or Bank overspending MUST not remain in the
Category and MUST reduce the following month's Ready to Assign. Credit Card
overspending MUST not remain in the Category or reduce the following month's
Ready to Assign; it MUST remain as implicit debt represented by a negative
Credit Card balance.

#### Scenario: Carry positive Category Available
- **GIVEN** a Category has positive Available at the end of a month
- **WHEN** the next month's envelope is calculated
- **THEN** that amount is the next month's Category rollover and contributes to
  its Available.

#### Scenario: Apply Cash or Bank overspending to the next month
- **GIVEN** a Category is overspent by a Cash or Bank expense
- **WHEN** the following month's budget is calculated
- **THEN** the excess is absent from the Category and reduces that month's Ready
  to Assign.

#### Scenario: Represent Credit Card overspending as debt
- **GIVEN** a Category is overspent by a Credit Card expense
- **WHEN** the following month's budget is calculated
- **THEN** the excess is absent from the Category and Ready to Assign, and the
  Credit Card balance represents the implicit debt as a negative balance.

### Requirement: Chronological classification for mixed categories
When a Category contains expenses funded by both Cash or Bank and Credit Card
Accounts, the system MUST classify financing and excess in chronological order
by effective event timestamp. Transaction ID MUST be the tie-breaker when
timestamps are equal. The resulting classification MUST apply the Cash/Bank or
Credit Card overspending policy to the corresponding excess.

#### Scenario: Resolve equal-time mixed expenses
- **GIVEN** mixed Cash/Bank and Credit Card expenses have the same event time
- **WHEN** financing and excess are classified
- **THEN** expenses are ordered by transaction ID and the selected order
  determines which amount is financed and which is excess.

### Requirement: Simplified Credit Card treatment
A Credit Card purchase MUST be recorded as an `expense`. A Credit Card payment
MUST be recorded as a `Transfer` and MUST be excluded from expense and budget
activity. The system MUST NOT create payment categories or move amounts
automatically between Categories for a payment.

#### Scenario: Exclude a Credit Card payment from spending
- **GIVEN** a payment is posted to a Credit Card
- **WHEN** budget activity is calculated
- **THEN** it is treated as a Transfer, not an expense, and creates no payment
  category or automatic Category movement.

### Requirement: Native-currency card and budget reporting
Credit Card purchases and their implicit debt MUST remain in the native
currency of the Credit Card Account. When that currency differs from the Plan
reporting/budget currency, the amount MUST be excluded from budget totals and
shown explicitly as `unconverted` by currency; the system MUST NOT convert it
silently. A cross-currency Credit Card payment MUST retain both original
amounts and currencies plus explicit rate evidence in accordance with the
Transfers specification, and MUST remain excluded from expense and budget
activity.

#### Scenario: Show a foreign-currency card purchase as unconverted
- **GIVEN** a Plan reports in BOB and a Credit Card Account records a USDT
  purchase
- **WHEN** budget totals are calculated
- **THEN** the purchase remains in USDT, is excluded from BOB totals, and is
  shown as unconverted USDT activity.

### Requirement: Goal completion and funding status
For a target-balance goal, status MUST be `completed` when Available reaches or
exceeds the target. For a monthly-funding goal, status MUST be `funded` when
the month's Assigned reaches or exceeds the target. For a due-date goal, the
current month MUST count as one of the remaining months. The required
contribution MUST be calculated from the remaining shortfall divided by the
remaining months. If the due date is in the current month or has passed, the
required contribution MUST be the entire remaining shortfall. Status MUST be
`completed`, `on_track`, or `underfunded`: `completed` when the shortfall is
zero, `on_track` when the month's funding meets the required contribution, and
`underfunded` otherwise.

#### Scenario: Complete a target-balance goal
- **GIVEN** Category Available reaches its target balance
- **WHEN** goal status is calculated
- **THEN** the goal status is `completed`.

#### Scenario: Fund a monthly-funding goal
- **GIVEN** a month's Assigned reaches its monthly funding target
- **WHEN** goal status is calculated
- **THEN** the goal status is `funded`.

#### Scenario: Classify a due-date goal
- **GIVEN** a due-date goal has a positive shortfall and remaining months
- **WHEN** its required contribution and status are calculated
- **THEN** the required contribution is the shortfall divided by remaining
  months, and status is `on_track` when that month's funding meets it;
  otherwise status is `underfunded`.

#### Scenario: Fund a current or overdue due-date goal
- **GIVEN** a due-date goal is due in the current month or is overdue and has a
  positive shortfall
- **WHEN** its required contribution is calculated
- **THEN** the required contribution is the entire remaining shortfall.

## Acceptance criteria
Monthly envelope values, rollover, overspending, and all three target types are represented.
