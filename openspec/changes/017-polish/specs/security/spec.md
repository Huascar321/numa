# Security delta

## ADDED Requirements

### Requirement: Scoped secret and PIN protection
Integration secrets MUST remain server-side/encrypted and any PIN MUST use a modern password hash, not plaintext or reversible encryption.

#### Scenario: Settings display
- **WHEN** integration settings are displayed
- **THEN** metadata is shown without secret values.
