# Budgeting delta

## MODIFIED Requirements

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
