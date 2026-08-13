# Transfers Specification

## Purpose
Move value between accounts without reporting it as spending or income.

## Scope
Same- and cross-currency linked transfer legs.

## Business rules
Transfer legs MUST post atomically. Same-currency absolute amounts MUST match. Cross-currency transfers MUST retain original and received amounts/currencies, rate, source, and time. Transfers MUST NOT be income, expense, category activity, or budget activity.

## Data model
Transfer link with two legs and exchange evidence when currencies differ.

## Constraints
No transfer category is permitted.

## Non-goals
Automated exchange execution is a non-goal.

## Requirements
### Requirement: Atomic linked transfer
The system MUST commit both linked legs or neither.

#### Scenario: BOB to USDT transfer
GIVEN BOB sent and USDT received
WHEN the transfer posts
THEN both exact originals and exchange evidence MUST be retained atomically.

## Acceptance criteria
Transfers change balances but are excluded from income, expenses, and budgeting.
