# MCP Specification

## Purpose
Expose safe semantic finance reads to MCP clients.

## Scope
Read-only tools with strict schemas, bounds, pagination, and redaction.

## Business rules
MCP MUST allow no mutation, SQL, filesystem access, or HTTP access. Inputs MUST be schema-validated and bounded; outputs MUST be redacted. Suggested tools are `get_plan_summary`, `list_accounts`, `list_transactions`, `get_budget_status`, `get_analytics`, and `get_reconciliation_history`.

## Data model
Tool name, strict input schema, bounded result schema, pagination cursor, and redaction policy.

## Constraints
MCP authentication mode is UNVERIFIED. Secrets MUST never be returned.

## Non-goals
Arbitrary database querying, tools that mutate, and network proxying are non-goals.

## Requirements
### Requirement: Bounded semantic reads
Each tool MUST enforce authorization, schema bounds, and redaction before responding.

#### Scenario: Arbitrary SQL request
GIVEN a client requests SQL, filesystem, HTTP, or mutation
WHEN the request is received
THEN it MUST be rejected without exposing sensitive data.

## Acceptance criteria
Suggested read tools are bounded and prohibited operation classes are rejected.
