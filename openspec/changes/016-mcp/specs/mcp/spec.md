# MCP delta

## ADDED Requirements

### Requirement: Bounded semantic read server
MCP tools MUST be read-only, schema-validated, bounded, paginated where applicable, and redacted by default.

#### Scenario: Arbitrary SQL request
- **WHEN** a client requests SQL, filesystem, HTTP, or a secret
- **THEN** the request is rejected and no sensitive value is exposed.
