# Rules delta

## ADDED Requirements

### Requirement: Deterministic rules
Rules MUST have typed inputs, stable order, explicit evidence, and replayable results.

#### Scenario: Conflicting rules
- **WHEN** deterministic rules disagree
- **THEN** the conflict is surfaced or quarantined, never silently resolved.

### Requirement: Explicit QR glosa rules
Rules MAY classify a QR transfer subtype from an exact observed glosa value,
including the observed product-payment value, but MUST preserve raw glosa. They
MUST NOT synthesize `BM BM QR INTERBANCARIA` when glosa is absent. Optional AI
MAY suggest a category from non-default informative glosa only.

#### Scenario: Missing glosa
- **GIVEN** a QR candidate has no glosa
- **WHEN** deterministic rules execute
- **THEN** glosa remains null and the candidate remains reviewable.
