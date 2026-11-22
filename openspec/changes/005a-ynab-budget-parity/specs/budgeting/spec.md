# Budget continuity delta

## ADDED Requirements

### Requirement: Continuous Ready to Assign
Unassigned funds and overassignment MUST persist across months. Future assignments
MUST reserve current money; future income MUST NOT fund an earlier month. Prior
cash overspending MUST reduce subsequent Ready to Assign exactly once. Category
Available MUST remain signed in the overspent month and positive leftovers MUST
roll forward. Mixed cash/credit spending MUST fund cash first. Exact money,
Plan-local month boundaries and explicit unconverted reporting MUST be retained.

#### Scenario: Carry unassigned income
- **GIVEN** September income 1000 and assignments 800, without overspending
- **WHEN** October is viewed without new income or assignments
- **THEN** Ready to Assign MUST be 200.

#### Scenario: Reserve next month without forecasting income
- **GIVEN** 200 unassigned and 50 assigned next month
- **WHEN** the current month is viewed
- **THEN** Ready to Assign MUST be 150, regardless of future-dated income.

### Requirement: Credit card payment reserves
Each budget-currency Credit Card MUST have one protected payment category.
Funded purchases MUST move budget availability from spending to payment reserves;
unfunded purchases MUST remain visible as debt. Actual payments and reversals
MUST change reserves without creating spending. Direct assignments MUST support
old debt. Foreign currency cards MUST remain unconverted. Payment categories MUST
reject ordinary expense categorization and destructive identity changes.
Positive card balances MUST behave as spendable cash until exhausted; only the
debt-creating portion of a purchase MUST create a payment reserve. Debt-reducing
card income MUST NOT invent cash. Overpayment-created credit and same-currency
cash advances MUST expose the resulting available cash and negative reserves.

#### Scenario: Fund purchase and pay card
- **GIVEN** 100 assigned to food and a 30 card purchase
- **WHEN** the budget is read and a 20 bank-to-card payment is subsequently posted
- **THEN** food Available MUST be 70 and payment Available MUST change from 30 to 10,
  without treating the payment as a second expense.

#### Scenario: Spend a positive credit card balance
- **GIVEN** a card holds positive 100 and its category is funded with 100
- **WHEN** a 130 purchase is posted
- **THEN** 100 MUST be cash spending and 30 MUST be unfunded credit spending,
  with no automatic reserve for the positive-balance portion.

### Requirement: Atomic budget actions
Users MUST be able to set monthly Assigned, move available money between categories
or Ready to Assign, and fund a target. Actions MUST be Plan-scoped, atomic,
client-UUID-idempotent and auditable. Retries MUST reuse the original outcome;
conflicting reuse MUST return 409. Moves MUST reject insufficient source funds
and MUST NOT create account movements. Targets MUST be editable and removable.

#### Scenario: Retry money move
- **GIVEN** an action moves 25 from food to transport
- **WHEN** the identical action UUID is retried
- **THEN** the original result MUST return without another pair of assignments.
