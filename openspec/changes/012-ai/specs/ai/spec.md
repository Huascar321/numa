# AI delta

## ADDED Requirements

### Requirement: Optional bounded AI
AI MUST remain optional and MUST NOT create final transactions or alter money, accounts, or timestamps.

#### Scenario: AI unavailable
- **WHEN** AI is disabled or a provider fails
- **THEN** deterministic processing remains usable and no financial mutation occurs.

### Requirement: Local schema validation
Provider output MUST pass local JSON-schema validation before becoming a reviewable suggestion.

#### Scenario: Invalid output
- **WHEN** structured output fails validation
- **THEN** it is rejected/quarantined.

### Requirement: Bounded QR glosa inference
AI MAY suggest a category from a non-default informative BCP QR glosa, but MUST
not synthesize missing glosa, overwrite raw glosa, or change money, account,
timestamp, direction, or final transaction data.

#### Scenario: Missing or default glosa
- **GIVEN** a QR candidate has missing glosa or the common default glosa
- **WHEN** AI suggestions are generated
- **THEN** no glosa is invented or overwritten and any suggestion remains optional and reviewable.
