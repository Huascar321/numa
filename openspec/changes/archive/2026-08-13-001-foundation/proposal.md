## Why

Establish an executable platform boundary before financial features are added.
Later phases need a buildable client, a configurable authoritative server, and
durable PostgreSQL-backed work that remains safe across retries and restarts.

## What Changes

Implement the initial React + TypeScript + Vite scaffold and FastAPI monolith;
add typed server configuration, PostgreSQL connectivity and migrations,
exact-money primitives, durable idempotent jobs, a restart-recoverable Python
worker, operational health endpoints, and graceful operation without optional
AI, Gmail, or exchange configuration.

## Capabilities

### New Capabilities

- `specs/architecture/spec.md`
- `specs/database/spec.md`

### Modified Capabilities

- None.

## Impact

Creates the initial `web/` and `api/` application structure, the PostgreSQL
baseline migration, and the automated checks for persistence, idempotency,
restart recovery, and unavailable optional dependencies. All later capabilities
depend on these boundaries.
