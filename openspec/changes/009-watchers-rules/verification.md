# Watcher/rule foundations — partial verification, 2026-10-08

## Scope and progress

The user requested continuing automatable work while postponing human notice
review. Tasks **9.1 and 9.2** are implemented and verified. **9.3 and 9.4 remain
unchecked**: the full phase includes provider MIME adapters and their evidence
boundaries; typed synthetic provider facts do not establish those implementations.
No change is being silently treated as a fully completed provider pipeline.

## Delivered foundations

- `api/app/watchers/contracts.py`: immutable typed source/provider facts, exact
  decimal strings, explicit timezone provenance, ordered stages, predicates,
  versioned classification-hint rules, rule evidence and pipeline results.
- `engine.py`: deterministic priority/ID/version order; applied/no-match/manual-
  protection evidence; incompatible proposals and duplicate rule IDs quarantined
  without choosing a winner; parser exception details scrubbed. Optional AI is
  skipped, and the transaction stage is always blocked. No financial service is
  imported or invoked.
- Rules can propose only category/subtype hints, not amounts, currencies,
  accounts, event times, glosa or settlement. Missing/unrecognized QR glosa never
  receives a default subtype; no real QR ruleset or optional AI was activated.
- Ganadero typed notices retain Bs→BOB, direction, masked suffix, notification
  metadata and authentication provenance. They reject invented payee/glosa/event
  time/transaction IDs and require statement enrichment. BCP typed facts retain
  supplied IDs, parties, raw glosa, MIME charset and explicit timezone provenance.
  These are **data contracts, not claims that new email parsers are operational**.
- `models.py` / `service.py` and `009_watcher_runs`: immutable stage/config/result
  snapshots referencing original Gmail evidence, input/ruleset fingerprints,
  Plan ownership checks, idempotent initial execution and explicit replay lineage.
  Source-message row locks serialize concurrent retries/replays. Changed rule
  contracts preserve earlier versions rather than overwriting them.
- Durable JSON results normalize tuple/enum representations so loaded evidence
  matches the original result after PostgreSQL round trips.

## Checks

- `.venv/bin/python scripts/run_postgres_tests.py -q`: **295 passed, 0 skipped**,
  including 30 new watcher tests (25 pure contracts/engine and 5 PostgreSQL
  storage checks). The randomly created test database was removed after the run.
- Coverage includes stable ordering and replay, conflicts, manual protection,
  scrubbed parser errors, absence of invented provider facts, Plan isolation,
  transactions rolling back records, DB immutability, concurrent retries/replays
  and preservation of raw references without financial mutations.
- Existing Gmail, Binance Card and financial suites remain green. Existing
  non-failing Starlette/httpx warning remains.
- Frontend regression: **23 tests passed**, TypeScript/Vite build passed.
  No UI code or visual tokens were changed by this foundation work.
- `openspec validate 009-watchers-rules --strict` and `git diff --check`: passed.

## Local rollout boundaries

Applied only additive schema `008_binance_review → 009_watcher_runs` on the
isolated development service at **39747**, separate from tests at **29746**.
Compared before/after row hashes for plans, accounts, transactions, movements,
assignments, correction history, existing Gmail evidence and existing Binance
review records: **unchanged**. Concurrently arriving messages were excluded from
the comparison by the original message-ID ceiling; existing evidence was not.

The new table contains **zero development runs**: this foundation is not wired
into live provider processing or exposed through a rule/replay API yet. Existing
Gmail/Binance ingestion remains as implemented in phases 007/008. No notices were
approved, discarded, reparsed or converted into financial records. No new sender,
Google authorization, parser activation or remote service was configured.

API restarted after checking its executable and working directory, retaining
`--no-access-log`. Readiness checks cover direct API **39748** and Vite proxy
**5173**. The worker/web were not stopped or replaced for this schema-only change.
No commits, push, archive or publishing occurred. Temporary rollout code was
removed and exported no original source messages or credentials.

## Remaining work without conflating human notice review

Integration with confirmed provider parsers, controlled automatic execution and
end-to-end provider validation remain in 9.3/9.4. BCP collection stays excluded
until the sender/subject contract is confirmed; current typed fixtures do not
authorize widening the Gmail sender scope. The existing 008 notice decisions and
settlement mappings can remain pending while these technical integrations are
worked on. No human review was requested or performed in this session.
