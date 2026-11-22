# Tasks

## 1. Sender scope and migration

- [x] 1.1 Add validated empty-by-default sender settings and fail-closed authorization; verify normalization, invalid inputs, empty configuration and optional-provider tests.
- [x] 1.2 Persist the effective per-connection list with a follow-up migration and update expected readiness revision; verify clean migration, legacy connection fencing and preserved evidence in PostgreSQL tests.

## 2. Filtered synchronization

- [x] 2.1 Build full-sync sender query and validate minimal From/label metadata before raw download for full/History; verify approved senders, display-name spoofs, ambiguous/malformed/missing headers, metadata 404, SPAM/TRASH and excluded-message non-persistence.
- [x] 2.2 Preserve the saved filter across pagination, retries, restarts and 404 recovery; adopt new settings only on reconnection; verify cursor progression, idempotency, stale jobs and retained evidence with PostgreSQL coverage.

## 3. Visible scope and local development

- [x] 3.1 Expose configured/effective sender lists and show safe scope explanations in Gmail UI; verify disabled empty configuration, scope display and existing actions in frontend tests/build.
- [x] 3.2 Add isolated PostgreSQL development Compose/env template, ignore secrets and support a configurable Vite API target; verify rendered Compose binds loopback high port with separate project/volume and documented startup never resets test data.
- [x] 3.3 Document filtered ingestion, sender-only limitations, reconnection and exact dev/callback ports; verify commands and security caveats match implemented behavior.

## 4. Integration validation and startup

- [x] 4.1 Run full backend suite on disposable PostgreSQL, frontend tests/build and strict OpenSpec/diff checks; record actual results and any remaining limitations.
- [x] 4.2 Check ports, configure ignored local files without replacing OAuth/Fernet credentials, start dev PostgreSQL/migrations/API/worker/web, and verify direct/proxied health plus browser UI without authorizing or collecting real mail; report running services/ports and safe stop commands.
