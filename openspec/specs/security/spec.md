# Security Specification

## Purpose
Protect personal financial data and integration credentials.

## Scope
Server secrets, OAuth, imports, query safety, PIN protection, and MCP redaction.

## Business rules
OAuth refresh tokens and API keys MUST remain server-side and encrypted. OAuth MUST use state and PKCE as applicable. Imports MUST be validated; queries MUST be safe. PINs MUST use Argon2id. Personal single-user auth mode and MCP auth mode are UNVERIFIED.

## Data model
Encrypted credential record, OAuth session state, PIN verifier, import validation result, and redaction policy.

## Constraints
No enterprise scope is included. Secrets MUST NOT appear in logs, clients, MCP output, or artifacts.

## Non-goals
Enterprise IAM, multi-tenant administration, and secret export are non-goals.

## Requirements
### Requirement: Server credential boundary
The system MUST encrypt integration credentials server-side and redact secret-shaped responses.

#### Scenario: Secret-shaped MCP field
GIVEN a semantic result contains a credential field
WHEN MCP responds
THEN the field MUST be omitted or redacted.

## Acceptance criteria
Credential encryption, OAuth protections, validated imports, safe queries, and Argon2id PIN storage are specified.
