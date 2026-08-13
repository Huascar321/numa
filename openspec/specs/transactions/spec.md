# Transactions Specification

## Purpose
Record correctable, provenance-preserving ledger activity.

## Scope
Income, expense, transfer, and reconciliation adjustment records.

## Business rules
Every Plan MUST have immutable, nondeletable `Pending`. Transactions MUST NOT have `cleared`. They MAY hold photos, memo, tags, opt-in location, merchant, source, metadata, and provenance. Corrections MUST preserve prior values and history.

## Data model
Transaction includes type, account movement, exact amount/currency, time, category where applicable, attributes, source, and correction events.

## Constraints
Amounts MUST never be floats. Human corrections MUST remain reviewable.

## Non-goals
Silent mutation of imported financial facts is a non-goal.

## Requirements
### Requirement: Correctable categorized transactions
Uncategorized applicable transactions MUST use the Plan's Pending category.

#### Scenario: Imported merchant correction
GIVEN an imported expense
WHEN its merchant is corrected
THEN imported value, corrected value, and correction event MUST remain reviewable.

## Acceptance criteria
Pending protection, allowed types, and correction history are enforced.
