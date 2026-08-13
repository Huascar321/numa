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

## Acceptance criteria
Monthly envelope values, rollover, overspending, and all three target types are represented.
