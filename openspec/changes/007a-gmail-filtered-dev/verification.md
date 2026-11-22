# Verification — 2026-10-07

## Automated checks

- Backend: `.venv/bin/python scripts/run_postgres_tests.py -q` — **221 passed,
  0 skipped**. The runner created and removed a disposable database on the
  PostgreSQL 18 test service at 29746, not the development database.
- Focused sender/settings/Gmail/migration run: **60 passed** before the additional
  regression cases; all later cases are covered by the full run above.
- Frontend: `npm test -- --run` — **13 passed**; `npm run build` passed.
- `openspec validate 007a-gmail-filtered-dev --strict` passed.
- `git diff --check` passed; reviewed settings/migration/API/UI/config/test changes
  and preserved prior uncommitted work.
- First full backend run found one stale head-revision assertion in reconciliation
  tests. It was updated to `007a_gmail_filter` and the complete suite rerun.

Coverage includes exact senders, display-name spoofing, malformed/missing/duplicate
From headers, multiple mailboxes, spam/trash, metadata 404 and transient errors,
no body download/storage for rejected full/History candidates, minimal metadata
fields, page rollback/retry, saved scope across new worker sessions and 404 recovery,
explicit reconnection, retention/deduplication and legacy migration fencing.

## Local runtime checks

- Ports 39747, 39748 and 5173 were free before starting.
- Rendered Compose was checked without printing credentials: PostgreSQL 18,
  project `numa-dev-postgres-18`, database/user `numa_dev`, loopback-only port 39747,
  independent volume `numa-dev-postgres-18_numa-dev-postgres-18-data`.
- Started `numa-dev-postgres-18-postgres-1`, healthy at `127.0.0.1:39747`.
  Existing test container remained healthy at `127.0.0.1:29746`.
- Applied migrations to the development database; verified head
  `007a_gmail_filter`, valid OAuth configuration and the approved sender list.
- API: PID **62835**, `127.0.0.1:39748`, access logging disabled.
- Worker: PID **62836**, using the same server settings.
- Vite: PID **62862**, `localhost:5173`, strictPort enabled.
- Direct `/health/live`, direct `/health/ready` and proxied `/health/ready` returned
  `{"status":"ok"}`; proxied `/plans` returned `[]`; currencies returned BOB/USDT.
- An independent Vite config resolution with `NUMA_API_TARGET` confirmed the
  configurable proxy. A second dev-server launch failed with
  `Port 5173 is already in use`, leaving the running server healthy.
- Disposable Playwright browser opened the SPA, which reached `/plans`, loaded
  currencies and displayed `No Plans yet.` through real API calls. Browser closed
  after verification; no Plan or Google authorization was submitted.
- Development `.env.numa-dev` and `api/.env` are ignored by Git and mode 0600.
  Existing unrelated configuration, OAuth credentials and Fernet key were checked
  unchanged. The temporary configuration script was removed.

## Remaining limitations

- No Google mailbox has been authorized; development has zero Gmail sources and
  zero messages. Real consent, ingestion and real-mail deduplication remain untested.
- Permission remains mailbox-wide readonly. The filter is local and sender-only;
  it neither authenticates senders nor distinguishes financial from other notices
  from the approved addresses. No Gmail-to-transaction parsing is activated.
- Testing-mode refresh tokens expire after seven days and require reconnection.
- Existing non-failing Starlette/httpx deprecation and Pydantic alias warnings
  remain. The browser also reported missing `/favicon.ico` (404); application
  data requests and the SPA succeeded. The favicon is outside this change.
- No commit, push, archive, billing change or OAuth publishing was performed.

## Stop the services started in this verification

These PIDs identify only this run; verify paths before using them later because
operating systems reuse PIDs:

```sh
ps -p 62835,62836,62862 -o pid=,command=
# Once confirmed to be the Numa API, worker and Vite processes above:
kill -TERM 62835 62836 62862
docker compose --env-file .env.numa-dev -f docker-compose.numa-dev.yml stop
```

Do not remove the development volume or stop unrelated projects. Restart commands
are in README.md. The approved allowlist is `do-not-reply@ses.binance.com` and
`notificaciones@bg.com.bo`; it is ready for the user's manual Gmail connection.
