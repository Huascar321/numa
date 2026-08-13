# Statements delta

## ADDED Requirements

### Requirement: Banco Ganadero structural validation
The parser MUST preserve source row/order and validate the verified four-sample
BOM, CRLF, semicolon, preamble/header/footer, date/time, numeric, and quoted
description structure. Footer debit/credit counts and balance chains are
verified for April through July. `SALDO ACTUAL` MUST be stored as current/as-of-
export balance, not period ending balance. Card suffixes `BO`, `FR`, and `US`
are metadata, not ledger currency.

#### Scenario: Current balance is not period ending balance
- **GIVEN** period balances chain correctly and `SALDO ACTUAL` differs from the final period balance
- **WHEN** dry run completes
- **THEN** it stores current/as-of-export metadata and creates no reconciliation adjustment.

### Requirement: Compound statement identity
Transaction ID alone MUST NOT identify a statement row. The parser MUST retain
source row/order and distinguish reused interest-credit and IVA-debit IDs.

#### Scenario: Reused transaction ID
- **GIVEN** an interest credit and IVA debit share one transaction ID
- **WHEN** rows are normalized
- **THEN** both source rows remain distinct and source order is retained before chain validation.

### Requirement: Side-effect-free dry run
Dry run MUST preview candidates, matches, warnings, and blockers without ledger effects; commit MUST be transactional and idempotent.

#### Scenario: Recommit
- **WHEN** the same compound source identity is submitted twice
- **THEN** no duplicate rows are posted.

## Evidence

Only sanitized structural observations are permitted. Additional account/export
versions and embedded semicolon, escaped-quote, or multiline variants
**REQUIRES REAL SAMPLE**.
