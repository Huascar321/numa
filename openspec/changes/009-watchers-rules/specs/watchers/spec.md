# Watchers delta

## ADDED Requirements

### Requirement: Ordered replayable pipeline
Watcher processing MUST preserve stage outcomes and follow Email → Watcher → Parser → Rules → optional AI → Normalize → Deduplicate → Transaction.

#### Scenario: Stage failure
- **WHEN** a parser or rule fails
- **THEN** the source is quarantined with a reviewable error and raw-safe reference.

### Requirement: Provider notice uncertainty
Banco Ganadero notices MUST preserve raw `Bs` amounts mapped to BOB, direction,
and masked account suffix, but MUST remain Pending/reviewable because they lack
payee, glosa, bank transaction ID, and authoritative event timestamp. BCP QR
notices MUST preserve transaction ID, receipt ID, event date with timezone
provenance, parties/accounts, BOB amount, and raw glosa. MIME charset and
notification time remain provenance fields.

#### Scenario: Bank notification date
- **GIVEN** a Banco Ganadero notice has only a header notification date
- **WHEN** a candidate is normalized
- **THEN** that date is not used as transaction event time and the candidate awaits statement enrichment.
