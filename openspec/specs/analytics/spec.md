# Analytics Specification

## Purpose
Provide plan-scoped financial reporting with explicit period, currency, and
transfer-treatment boundaries for reliable interpretation.

## Scope
Income, expense, net, balances, comparisons, categories, merchants, tags, trends, heatmaps, and goal status.

## Business rules
Analytics MUST be Plan and period scoped. Transfers MUST be excluded from income and expense. Unconverted values MUST be explicit rather than silently aggregated.

## Data model
Report query, period, plan, metric, currency state, grouping, and result.

## Constraints
Reporting MUST use the Plan reporting currency only when authorized conversion exists.

## Non-goals
Cross-plan or silent FX aggregation is a non-goal.

## Requirements
### Requirement: Explicit reporting boundaries
The system MUST label unconverted data and exclude transfer legs from income/expense totals.

#### Scenario: Mixed-currency report
GIVEN a report includes a transfer and an unconverted amount
WHEN totals are computed
THEN the transfer MUST be excluded and unconverted state MUST be visible.

## Acceptance criteria
Requested metrics are available within stated plan, period, and currency boundaries.
