# Security delta

## ADDED Requirements

### Requirement: MCP secret boundary
MCP MUST never expose OAuth refresh tokens, API keys, or other secrets.

#### Scenario: Secret-shaped result
- **WHEN** a semantic result contains a secret field
- **THEN** the field is omitted or redacted before response.
