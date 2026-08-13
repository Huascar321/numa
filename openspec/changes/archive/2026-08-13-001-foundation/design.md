# Design

## Context

The repository has no application scaffold. This change establishes the
executable foundation for subsequent finance capabilities without introducing
plans, accounts, transactions, Gmail ingestion, AI, or exchange integrations.

## Goals

- Create a React + TypeScript + Vite client in `web/` and a FastAPI monolith in
  `api/`.
- Make PostgreSQL the authoritative durable store with Alembic migrations.
- Establish reusable exact-money, idempotency, job-processing, worker, and
  operational-health boundaries.
- Permit startup and basic health operation when AI, Gmail, and exchange
  settings are absent.

## Non-Goals

- Plans, accounts, ledger records, financial mutations, Gmail ingestion, AI,
  exchange-rate retrieval, and PWA/offline behavior belong to later changes.
- Redis, Kafka, microservices, client-authoritative state, and destructive job
  history are excluded.

## Decisions

### Application layout and authority

`web/` contains the Vite React TypeScript application and its build/test
configuration. `api/` contains one FastAPI application, its Python dependency
configuration, domain-independent infrastructure modules, tests, and a Python
worker entry point. The client consumes server responses as authoritative and
does not own financial state.

### Typed configuration and optional integrations

The API loads a typed settings model from environment variables. `DATABASE_URL`
is required for database-backed readiness and worker execution. Server-side
configuration is the only place secrets may be loaded. AI, Gmail, and exchange
settings are optional: their absence disables no startup path, route, migration,
or worker dependency in this change. A checked-in `.env.example` documents only
variable names and safe example values.

### PostgreSQL and migrations

The API owns one PostgreSQL connection/session boundary and Alembic owns schema
history. A fresh database must reach the initial schema through `alembic upgrade
head`; the migration must also be safe to apply to a database already at that
revision. Tests run against PostgreSQL rather than a different SQL dialect for
claiming and locking behavior.

### Exact money

The shared money primitive accepts `Decimal` values or integer atomic units and
rejects Python `float` values. Any persisted monetary column introduced by this
foundation or later migrations uses PostgreSQL `NUMERIC` or an integer atomic
column; `REAL`, `DOUBLE PRECISION`, and floating-point serialization are not
valid money representations. This change does not create a financial ledger
table; it supplies the primitive and persistence policy that those tables use.

### Durable jobs and idempotency

The initial migration creates a durable `jobs` table with a stable identifier,
job type, payload, status, idempotency key, request fingerprint, attempt count,
maximum attempts, next-available timestamp, lease expiry, claimant identity,
current claim token, timestamps, completion timestamp, and retained failure
details. Statuses are `queued`, `running`, `succeeded`, and `failed`. A
uniqueness constraint on job type plus idempotency key makes repeated enqueue
attempts return the original durable job; a reused key with a different request
fingerprint is rejected without altering the original job.

A worker claims one eligible job in a PostgreSQL transaction using row locking
with `SKIP LOCKED`, records its lease and attempt, and commits before executing
the handler. Every worker instance has a unique claimant identifier, and every
claim attempt replaces the job's claim token with a newly generated fencing
token. Completion and failure operations accept only the current claim token;
after an expired lease is reclaimed, an older attempt cannot modify the job's
status, lease, claimant, attempt count, or failure history. Retryable failure
returns the job to `queued` with a later next-available timestamp; a terminal
failure remains `failed` with its error history. Expired `running` leases are
eligible for reclamation, so a process restart cannot strand a job.

### Wake signals and worker recovery

An enqueue transaction persists the job before emitting PostgreSQL
`LISTEN/NOTIFY`. Notifications only wake an already polling worker; lost,
duplicated, or delayed notifications do not affect job correctness. The Python
worker polls eligible and expired-lease jobs on startup and between wake-ups,
so it recovers work after restart without any external queue.

### Operational health

`GET /health/live` proves that the FastAPI process can serve requests and does
not require PostgreSQL. `GET /health/ready` verifies database connectivity and
that the expected migration revision is available; it reports unavailable when
PostgreSQL is unreachable. These endpoints do not expose secrets or optional
provider configuration.

## Verification Strategy

Automated checks must build the web scaffold, exercise FastAPI liveness and
readiness, migrate a fresh PostgreSQL database, reject floating-point money,
prove idempotent enqueue behavior, prove concurrent transactional claims do not
duplicate a claim, prove an expired lease is reclaimed after worker restart, and
prove stale completion and failure attempts are fenced after reclamation. Tests
also start the API with AI, Gmail, and exchange configuration omitted and confirm
that basic health behavior remains available.
