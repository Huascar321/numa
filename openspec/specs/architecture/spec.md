# Architecture Specification

## Purpose
Define the fixed personal-finance application boundary and durable processing model.

## Scope
React 19 + TypeScript + Vite 8 SPA/PWA, React Router, TanStack Query/Virtual, custom Workbox service worker; FastAPI monolith; PostgreSQL 18; and its Python worker role.

## Business rules
The server MUST be authoritative. Offline writes MUST use only an idempotent outbox. PostgreSQL jobs are durable; LISTEN/NOTIFY is only a wake signal. The same application process SHOULD host the Python worker role.

## Data model
Durable jobs and idempotency keys are PostgreSQL records.

## Constraints
No microservices, Redis, or Kafka without an ADR. The PWA MUST remain usable without AI, Gmail, or an exchange provider.

## Non-goals
Distributed event infrastructure and client-authoritative accounting are non-goals.
## Requirements
### Requirement: Durable monolith
The application MUST use the scoped stack and recover pending PostgreSQL jobs after restart.

#### Scenario: Missed wake signal
GIVEN a durable queued job and a missed notification
WHEN a worker restarts
THEN it MUST discover and process the job from PostgreSQL.

### Requirement: Executable authoritative application scaffold
The repository MUST contain a React + TypeScript + Vite client in `web/` and one
FastAPI monolith in `api/`. The client MUST treat server responses as
authoritative; the change MUST NOT introduce microservices, Redis, Kafka, or
client-authoritative financial state.

#### Scenario: Baseline application build and liveness
- **GIVEN** a developer installs the declared web and API dependencies
- **WHEN** the web build and API liveness check are run
- **THEN** the React TypeScript bundle builds and `GET /health/live` returns a successful process-health response.

### Requirement: Typed server configuration with optional integrations
The FastAPI application MUST load typed configuration from environment variables.
Database configuration MUST remain server-side, and the checked-in environment
template MUST contain no secrets. AI, Gmail, and exchange configuration MUST be
optional and MUST NOT be required to create the application, serve liveness, or
run the durable-job worker.

#### Scenario: Optional providers are unconfigured
- **GIVEN** AI, Gmail, and exchange environment variables are absent
- **WHEN** the application starts with valid database configuration
- **THEN** it serves its basic health endpoints without loading or contacting those providers.

### Requirement: Recoverable durable job worker
The application MUST provide a Python worker that obtains durable jobs from
PostgreSQL. It MUST persist a job before any wake signal, transactionally claim
eligible work, and recover expired claims after restart. Each worker instance
MUST use a unique claimant identifier, and each claim attempt MUST receive a new
fencing token so an earlier execution cannot modify a reclaimed job. PostgreSQL
`LISTEN/NOTIFY` MUST be used only as a non-durable wake signal, never as the
source of job state or delivery guarantee.

#### Scenario: Worker restart
- **GIVEN** a queued job or an expired running-job lease in PostgreSQL
- **WHEN** a worker starts after missing a notification or after a previous worker stops
- **THEN** it discovers and claims the recoverable job from PostgreSQL without relying on notification delivery.

### Requirement: Liveness and readiness separation
The application MUST expose `GET /health/live` for process liveness and `GET
/health/ready` for PostgreSQL readiness and migration availability. Health
responses MUST NOT disclose secrets or optional-provider settings.

#### Scenario: PostgreSQL is unavailable
- **GIVEN** the FastAPI process is running and PostgreSQL cannot be reached
- **WHEN** liveness and readiness endpoints are requested
- **THEN** liveness succeeds while readiness reports that the database dependency is unavailable.

## Acceptance criteria
The durable job and idempotent outbox boundaries are documented and enforced.
