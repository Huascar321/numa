# Review-only Binance Card verification — 2026-10-08

## Approved scope

The user approved initial purchase candidates for inspection only, without
financial movements or USD→USDT conversion. Proposal/design/specs/tasks were
updated coherently before implementation. Missing real samples, settlement,
account mapping, financial approval/posting and cross-mailbox semantic merges
remain deferred. Completion refers only to this initial scope.

## Automated checks

- `.venv/bin/python scripts/run_postgres_tests.py -q`: **265 passed, 0 skipped**,
  on a newly created/disposed PostgreSQL 18 database at test port 29746. Includes
  fixture/MIME checks, positive/negative parser cases, exact strings, nested MIME,
  hidden/head HTML exclusion, merchant punctuation/entities, immutable storage,
  nullable-currency constraint, atomic ingestion rollback/replay, concurrent
  backlog processing, source preservation, pagination and Plan isolation. The
  full existing financial/Gmail suites still pass.
- `npm test -- --run`: **23 passed**. New coverage includes exact large USD
  strings, safe merchant text rendering, no posting controls, cursor pagination,
  unsupported notices with no inferred amounts, Plan-specific cache and retry UI.
- `npm run build`: TypeScript and Vite build passed.
- Strict phase-008 OpenSpec validation and `git diff --check` passed.
- Existing non-failing Starlette/httpx deprecation and Pydantic alias warnings
  remain; no dependency changes were required for this phase.

## Browser checks

Read-only synthetic request interception blocked mutations and avoided exposing
real messages. Reviewed desktop/mobile screenshots and the Gmail review section
at **320, 390 and 1440px**, with no horizontal overflow or console errors. Checked
cursor load-more, native disclosure by mouse/keyboard, reduced motion, mobile
last-action clearance and open provenance at **320px / 200% root text size**.
Fixed provenance column compression by stacking its labels/values on mobile.

## Local rollout

- Development PostgreSQL remained at **39747**, separate from tests; upgraded
  `007a_gmail_filter → 008_binance_review` additively, without dropping data.
- Processed **213** previously stored messages in bounded batches:
  **25 candidates**, **15 needs-review notices**, **173 ignored**.
- Reasons: 25 unresolved-settlement USD candidates; 4 unsupported amount forms,
  3 unsupported currencies, 1 unsupported success body, 7 unsupported Card
  subjects; 10 failures, 117 other-sender and 46 unrelated notices ignored.
  Thus 8 of the 33 success-subject notices need inspection, not automatic posting.
  No additional supported-template/currency claim follows from these counts.
- Compared before/after hashes of full rows in plans, accounts, transactions,
  movements, assignments and correction history: **unchanged**. Also compared
  complete stored Gmail evidence (raw MIME hash, decoded/provider metadata,
  identity, status and ingest time): **unchanged** across migration/backfill.
- Plan read API/readiness verified locally without printing message bodies,
  merchant names, amounts, dates, mailbox addresses or credentials.
- Started API/worker/web after checking ports/process paths. Direct and proxied
  `/health/ready` returned `{"status":"ok"}`. API access logs are disabled to
  avoid OAuth callback query logging. No Google authorization was changed.
- Subsequent runtime summary: **216** stored messages, **25 candidates**, **15
  needs-review**, **176 ignored**; connection active in History mode with no
  current error. Worker processed three new messages. Financial totals remained
  **0 transactions / 0 movements**. These are point-in-time counts.

## Local running processes and shutdown

At verification time: API **65027**, worker **64708**, Vite **63761**. PIDs can be
reused: confirm `ps -p <pid> -o command=` and `lsof -a -p <pid> -d cwd -Fn` point
to this repository before `kill -TERM <pid>`. Do not stop unrelated projects.
Container shutdown can use
`docker compose --env-file .env.numa-dev -f docker-compose.numa-dev.yml stop` from
the root. Never use `down -v` or remove the development volume for routine stops.

No commit, push, archive, remote publication or financial posting was performed.
The temporary local rollout script was removed; it wrote no original-email files.
