# Budgeting delta

## ADDED Requirements

### Requirement: Rollover and goal status
Budget months MUST support rollover, cash overspending policy, and goals with target balance, monthly funding, due date, and status.

#### Scenario: Unconverted amount
- **WHEN** an amount lacks an authorized quote
- **THEN** budget totals exclude it or label it unconverted rather than silently converting.
