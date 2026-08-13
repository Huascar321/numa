# Reconciliation Specification

## Purpose
Reconcile derived balances with a retained audit trail.

## Scope
Preview, explicit confirmation, and reconciliation adjustments.

## Business rules
The system MUST preview the discrepancy between derived and statement balance before any adjustment. An adjustment MUST require explicit confirmation and retain reconciliation history.

## Data model
Reconciliation session: account, statement balance/date, derived balance, discrepancy, status, and optional adjustment.

## Constraints
The system MUST NOT invent a reconciliation to resolve imported conflicts.

## Non-goals
Automatic discrepancy posting is a non-goal.

## Requirements
### Requirement: Preview-first adjustment
The system MUST post at most one confirmed adjustment atomically per confirmed session.

#### Scenario: Confirm mismatch
GIVEN a displayed discrepancy
WHEN the user explicitly confirms it
THEN a protected adjustment and audit event MUST be retained.

## Acceptance criteria
Preview precedes posting and retained history identifies every confirmed adjustment.
