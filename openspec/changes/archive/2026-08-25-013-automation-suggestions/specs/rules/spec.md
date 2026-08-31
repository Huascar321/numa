# Rules delta

## ADDED Requirements

### Requirement: Auditable rule suggestion
Rule-derived automation MUST be deterministic, replayable, and limited to explicitly allowed actions.

#### Scenario: Accepted rule
- **WHEN** a user accepts a rule suggestion
- **THEN** its evidence and decision are retained for later replay.

### Requirement: Bounded QR subtype suggestion
An exact observed QR glosa MAY drive a deterministic subtype suggestion, but the
rule MUST preserve raw glosa and MUST NOT synthesize the common default when the
field is absent.

#### Scenario: Missing glosa
- **GIVEN** a QR candidate lacks glosa
- **WHEN** a rule suggestion is evaluated
- **THEN** no glosa is created and the result remains reviewable.
