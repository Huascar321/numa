# Reconciliation delta

## ADDED Requirements

### Requirement: Preview-first reconciliation
The system MUST preview discrepancy between derived and statement balance before posting.

#### Scenario: Confirm mismatch
- **WHEN** the user explicitly confirms a preview
- **THEN** one protected adjustment posts atomically and the event remains auditable.
