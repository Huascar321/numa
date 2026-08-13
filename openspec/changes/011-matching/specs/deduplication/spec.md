# Deduplication delta

## ADDED Requirements

### Requirement: Four-way auditable classification
Candidates MUST be classified EXACT_MATCH, HIGH_CONFIDENCE_MATCH, POSSIBLE_MATCH, or NEW_TRANSACTION using documented signals.

#### Scenario: Possible match
- **WHEN** signals are similar but inconclusive
- **THEN** it remains separate and awaits review.

### Requirement: Provenance-preserving enrichment
Statement enrichment MAY add source fields but MUST preserve manual fields and all provenance.

#### Scenario: Manual record enrichment
- **WHEN** a statement matches a manual record
- **THEN** manual content and source history remain intact.

### Requirement: Notification-to-statement enrichment
A Banco Ganadero notice candidate MUST remain separate and reviewable until it
matches a statement record. Matching MAY add statement payee, glosa, bank ID,
and event time, but MUST preserve notification time, raw notice fields, and
provenance.

#### Scenario: Inconclusive bank notice match
- **GIVEN** a notice supplies only notification time and matching is inconclusive
- **WHEN** enrichment runs
- **THEN** no transaction event time is inferred and the candidate remains separate.
