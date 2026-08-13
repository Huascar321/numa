# Database Specification

## Purpose
Define exact, durable financial persistence for plan-scoped records, provenance,
idempotency, and safe retry behavior.

## Scope
PostgreSQL 18 schemas for plan-scoped finance records, jobs, provenance, and retries.

## Business rules
Money MUST use decimal or integer atomic representation, never float. Retriable mutations MUST be idempotent and atomic.

## Data model
Records carry plan ownership, stable identifiers, timestamps, and idempotency or source identities where applicable.

## Constraints
Safe parameterized queries MUST be used; financial history MUST be retained.

## Non-goals
Cross-plan aggregation and destructive history rewrites are non-goals.
## Requirements
### Requirement: Exact retry-safe persistence
The database MUST persist one durable result per idempotency key.

#### Scenario: Repeated submission
GIVEN a completed mutation key
WHEN the same request is retried
THEN only the original durable result MUST exist.

### Requirement: PostgreSQL migration-owned persistence
The application MUST connect to PostgreSQL through one server-side persistence
boundary, and Alembic migrations MUST own the schema history. The initial
migration MUST create the durable jobs table and its constraints and indexes.

#### Scenario: Fresh database initialization
- **GIVEN** an empty PostgreSQL database configured for the API
- **WHEN** the migration command upgrades to head
- **THEN** the durable-jobs schema and Alembic revision state are created successfully.

### Requirement: Exact money representation
The shared money representation MUST accept decimal values or integer atomic
units and MUST reject floating-point values. Every persisted money column
introduced by this foundation MUST use PostgreSQL `NUMERIC` or an integer atomic
type; `REAL`, `DOUBLE PRECISION`, and floating-point money serialization MUST
NOT be used.

#### Scenario: Floating-point money is rejected
- **GIVEN** an attempt to construct or persist a money value from a Python float
- **WHEN** the money boundary is invoked
- **THEN** it rejects the value rather than rounding or storing it.

### Requirement: Durable idempotent jobs
The initial PostgreSQL schema MUST persist each job's stable identifier, job
type, payload, status, idempotency key, request fingerprint, attempts, maximum
attempts, next-available time, lease expiry, claimant identity, current claim
token, timestamps, completion time, and failure details. Status MUST be one of
`queued`, `running`, `succeeded`, or `failed`. A unique job-type and
idempotency-key constraint MUST allow one durable job per request identity.

#### Scenario: Repeated operation
- **GIVEN** an enqueue request has already created a durable job
- **WHEN** the same job type, idempotency key, and request fingerprint are submitted again
- **THEN** the original job is returned and no second durable job exists.

#### Scenario: Idempotency-key conflict
- **GIVEN** an idempotency key is already associated with a job type and request fingerprint
- **WHEN** the same key is submitted with a different fingerprint
- **THEN** the request is rejected and the original durable job remains unchanged.

### Requirement: Transactional claim and retry recovery
An eligible queued job or expired running lease MUST be claimed in one
PostgreSQL transaction using row-level locking that prevents two workers from
claiming the same job. A claim MUST record the claimant, lease, and attempt
before handler execution. Each worker instance MUST use a unique claimant
identifier, and each claim attempt MUST generate a new claim token that fences
earlier attempts. Completion and failure MUST accept only the current claim
token. After reclamation, an earlier attempt MUST NOT alter status, lease,
claimant, attempt count, or failure details. Retryable failure MUST schedule
another eligible attempt without creating a duplicate job, and terminal failure
MUST retain its failure details.

#### Scenario: Concurrent worker claim
- **GIVEN** two workers attempt to claim the same eligible job concurrently
- **WHEN** each executes the transactional claim operation
- **THEN** exactly one worker receives the claim and the other receives no claim for that job.

#### Scenario: Reclaimed attempt fences stale execution
- **GIVEN** a running job's lease expires and another worker reclaims it with a new claim token
- **WHEN** the earlier attempt submits completion or failure using its old token
- **THEN** both operations are rejected and the current claim state remains unchanged.

## Acceptance criteria
Duplicate retry behavior and exact-money storage are validated.
