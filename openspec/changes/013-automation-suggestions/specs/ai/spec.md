# AI delta

## ADDED Requirements

### Requirement: Reviewable automation suggestion
AI automation suggestions MUST carry evidence, version, provenance, and a human decision before use.

#### Scenario: Reject suggestion
- **WHEN** a user rejects a suggestion
- **THEN** no transaction or money field changes and the rejection remains recorded.

### Requirement: Bounded QR category suggestion
AI MAY suggest a category from informative non-default QR glosa only. It MUST
not create or overwrite raw glosa or infer missing glosa.

#### Scenario: Informative QR glosa
- **GIVEN** a QR candidate contains an informative non-default glosa
- **WHEN** AI proposes a category
- **THEN** the raw glosa remains unchanged and the category remains a human-reviewed suggestion.
