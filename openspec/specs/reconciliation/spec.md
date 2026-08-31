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

### Requirement: Exact Plan-scoped as-of comparison
The system MUST accept statement balance only as a plain decimal string in the
ledger `NUMERIC(38,18)` representation domain: optional minus sign, 1-20 integer
digits, and at most 18 fractional digits, further restricted to the selected
Account's immutable currency scale. It MUST reject exponent notation, overlong
or out-of-domain magnitudes, floats, and currency mismatch before rounding or
unbounded decimal parsing, and MUST require a string UTC `statement_at` using
exactly `Z` or `+00:00`.
It MUST derive the balance from movements in the same Plan, Account, and currency
whose `effective_at <= statement_at`, and MUST calculate `discrepancy =
statement_balance - derived_balance`.

#### Scenario: Inclusive as-of boundary
GIVEN same-Plan movements before, exactly at, and after a UTC statement timestamp
WHEN the user previews reconciliation
THEN the derived balance MUST include the first two movements, exclude the last, and return exact scale-formatted strings.

#### Scenario: Invalid statement money
GIVEN a float, exponent notation such as `1e999999`, an overlong or out-of-domain
decimal, a mismatched currency, or a decimal beyond the Account currency scale
WHEN the user requests a preview or confirmation
THEN the request MUST be rejected without a reconciliation session or ledger effect.

### Requirement: Side-effect-free preview and configured policy
Preview MUST create no durable row. The server MUST expose the effective policy
and exact tolerance. `RECONCILIATION_POLICY` MUST be exactly `block|warn` with
safe default `block`; `RECONCILIATION_TOLERANCE_ATOMS` MUST be a non-negative
integer with safe default `0`, interpreted in the Account's smallest currency
unit. Above tolerance, `block` MUST reject confirmation and `warn` MUST require
strict explicit warning acceptance; at or below tolerance either policy MUST
permit confirmation without acceptance.

#### Scenario: Repeated preview has no effects
GIVEN a client reconciliation-session UUID and valid statement facts
WHEN preview is requested repeatedly
THEN each response MUST reflect authoritative reads and no session, Transaction, or movement MUST be written.

#### Scenario: Warning requires acceptance
GIVEN `warn` policy and an absolute discrepancy above tolerance
WHEN confirmation omits or denies warning acceptance
THEN confirmation MUST be rejected without durable effects.

#### Scenario: Block rejects above tolerance
GIVEN `block` policy and an absolute discrepancy above tolerance
WHEN confirmation is requested even with warning acceptance
THEN confirmation MUST be rejected without durable effects.

### Requirement: Auditable idempotent confirmation
Confirmation MUST persist one immutable reconciliation session atomically. A
zero discrepancy MUST persist an auditable confirmation without a Transaction or
movement. A non-zero allowed discrepancy MUST post exactly one protected,
categoryless `reconciliation_adjustment` Transaction and one original movement
whose signed amount equals the discrepancy and whose effective time equals
`statement_at`.

Confirmation MUST lock the selected Account row before calculating the as-of
balance and hold that lock through commit. Every current service operation that
can insert Account movements (manual posting, correction, Transfer, reversal,
or reconciliation) MUST use the same row-lock boundary. Multi-Account writers
MUST lock Account UUIDs in deterministic ascending order.

#### Scenario: Concurrent movement writer
GIVEN a movement writer for the Account has acquired the shared serialization lock
WHEN reconciliation confirmation starts while that writer is uncommitted
THEN confirmation MUST wait, include the committed movement when it is at or before `statement_at`, and MUST NOT retain a falsely reconciled comparison.

#### Scenario: Confirm mismatch
GIVEN an active Account and a non-zero discrepancy permitted by policy
WHEN the user explicitly confirms the same statement facts
THEN one adjustment MUST post atomically, the resulting balance as of the timestamp MUST equal the statement balance, and immutable history MUST identify the adjustment.

#### Scenario: Confirm exact match
GIVEN a zero discrepancy
WHEN the user explicitly confirms
THEN immutable history MUST retain the comparison and no adjustment Transaction or movement MUST exist.

#### Scenario: UUID replay and concurrency
GIVEN one client reconciliation-session UUID
WHEN matching confirmations are retried sequentially or concurrently
THEN the persisted response MUST be the same and SQL uniqueness MUST leave at most one session and one adjustment.

#### Scenario: Conflicting UUID reuse
GIVEN a confirmed reconciliation-session UUID
WHEN it is reused with different statement facts or warning acceptance
THEN the request MUST return conflict and MUST NOT alter the original session or ledger.

### Requirement: Protected and budget-excluded adjustment
Reconciliation sessions and adjustments MUST be immutable, non-correctible, and
non-deletable in both service and SQL boundaries. Adjustments MUST have no
Category and MUST be excluded from budget, income, expense, transfer, and
unconverted activity while remaining included in the Account balance.

#### Scenario: SQL and service mutation guards
GIVEN a confirmed adjustment
WHEN a caller attempts generic correction, UPDATE, DELETE, or a second adjustment for the session
THEN service and SQL guards MUST reject it without changing history.

### Requirement: Archived Account and Plan isolation
An archived Account MUST permit historical preview and a zero-discrepancy
confirmation, but MUST reject a confirmation that would post an adjustment. All
reconciliation operations MUST be scoped by both Plan and Account.

#### Scenario: Archived zero and mismatch
GIVEN an archived Account
WHEN a zero discrepancy is confirmed and a non-zero discrepancy is separately confirmed
THEN the zero confirmation MUST be retained without a movement and the non-zero confirmation MUST be rejected without a session.

#### Scenario: Cross-Plan isolation
GIVEN an Account or reconciliation session owned by another Plan
WHEN preview, confirmation, or history is requested through the wrong Plan
THEN the system MUST return not found and disclose or mutate no reconciliation data.

## Acceptance criteria
Preview precedes posting and retained history identifies every confirmed adjustment.
