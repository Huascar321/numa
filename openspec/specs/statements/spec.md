# Statements Specification

## Purpose
Safely import Banco Ganadero statements using structural validation.

## Scope
CSV dry-run, review, and transactional idempotent commit.

## Business rules
The parser MUST handle the verified single-account, four-consecutive-month Banco Ganadero export structure: UTF-8 BOM, CRLF, semicolon delimiters, preamble/header/footer, quoted fields, DD/MM/YYYY, HH:MM:SS, decimal dot/comma grouping, and signs. Debit/credit counts and running arithmetic are verified for these samples, and their period balances form a valid chain. `SALDO ACTUAL` is a current/as-of-export balance, not a period-ending balance. Identity MUST be compound and retain source order; a monthly interest/IVA pair may reuse a transaction ID and appear out of chronological timestamp order. BO, FR, and US card suffixes in descriptions are metadata, not ledger currency.

## Data model
Import, source row/order, compound source identity, parsed candidate, warnings, review decision, and commit result.

## Constraints
Dry run MUST have no ledger effects. Commit MUST be transactional and idempotent. Additional account/export versions and embedded-semicolon, escaped-quote, or multiline variants REQUIRES REAL SAMPLE. Private CSV content MUST NOT be reproduced.

## Non-goals
Inventing reconciliation or relying on transaction ID alone is a non-goal.

## Requirements
### Requirement: Structural import validation
The system MUST validate footer debit/credit counts, running arithmetic, and the period balance chain against the verified four-month structure while retaining source order before validation. It MUST store `SALDO ACTUAL` separately as current/as-of-export metadata, MUST NOT compare it as period ending, and MUST NOT generate reconciliation from it.

#### Scenario: Current balance differs from period ending balance
GIVEN `SALDO ACTUAL` differs from the final period balance
WHEN dry run completes
THEN it MUST store the current/as-of-export value separately without a warning based solely on that difference or a reconciliation adjustment.

### Requirement: Compound statement identity and order
The system MUST use compound source identity, including source row/order, rather than transaction ID alone. It MUST preserve source order when a monthly interest credit and IVA debit reuse the same transaction ID, even if their timestamps would sort differently.

#### Scenario: Reused monthly interest and IVA identifier
GIVEN interest and IVA rows share a transaction ID and are out of chronological timestamp order
WHEN rows are normalized and validated
THEN both rows MUST remain distinct and in source order.

## Acceptance criteria
Dry run output includes candidates, matches, warnings, blockers, and source identities; recommit creates no duplicates.
