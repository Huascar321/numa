# Budgeting delta

## ADDED Requirements

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

## MODIFIED Requirements

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
