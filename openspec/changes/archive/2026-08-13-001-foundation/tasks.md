# Tasks

## 1. Application scaffold and configuration

- [x] 1.1 Create `web/` with the React + TypeScript + Vite scaffold, `src/main.tsx`, and build configuration; `npm run build` from `web/` produces a production bundle.
- [x] 1.2 Create `api/` with its Python dependency configuration, `app/main.py`, and typed `app/settings.py`; a checked-in `.env.example` documents `DATABASE_URL` and optional AI, Gmail, and exchange variables without secrets.
- [x] 1.3 Implement `GET /health/live` and `GET /health/ready` in `api/app/main.py`; API tests prove liveness is process-only and readiness reports an unreachable PostgreSQL dependency without exposing configuration values.

## 2. PostgreSQL, migrations, and exact money

- [x] 2.1 Add the PostgreSQL engine/session boundary in `api/app/db.py` and Alembic configuration in `api/alembic.ini`, `api/alembic/env.py`, and `api/alembic/`; upgrading a fresh PostgreSQL test database to head records the initial revision.
- [x] 2.2 Implement the shared exact-money primitive in `api/app/money.py`; unit tests prove it accepts `Decimal` or integer atomic units and rejects Python `float` values.
- [x] 2.3 Create the initial Alembic revision for the `jobs` table, job-status constraint, idempotency uniqueness constraint, and claim-lookup indexes; migration tests verify the expected schema and contain no floating-point money columns.

## 3. Durable jobs and recoverable worker

- [x] 3.1 Implement enqueue and idempotency handling in `api/app/jobs/`; PostgreSQL integration tests prove repeated matching requests return one durable job and conflicting request fingerprints leave the original job unchanged.
- [x] 3.2 Implement transactional claim, lease, claim-token fencing, retry scheduling, and terminal-failure retention in `api/app/jobs/`; PostgreSQL integration tests prove concurrent claims do not duplicate work and stale attempts cannot modify a reclaimed job.
- [x] 3.3 Implement the Python worker entry point in `api/app/worker.py` with a unique claimant ID per instance, startup polling, expired-lease recovery, and optional `LISTEN/NOTIFY` wake-ups; restart tests prove queued or expired jobs are processed after missed notifications without an external queue.

## 4. Dependency-outage behavior and verification

- [x] 4.1 Add API and worker configuration tests with AI, Gmail, and exchange variables absent; tests prove the app still starts, serves basic health behavior, and does not contact optional providers.
- [x] 4.2 Run the web build, API test suite, PostgreSQL migration tests, job idempotency/claim/fencing/restart tests, and `openspec validate 001-foundation --strict --no-interactive`; retain all task boxes as pending until their corresponding implementation and checks pass.
