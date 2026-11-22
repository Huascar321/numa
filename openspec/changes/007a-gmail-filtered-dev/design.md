# Design

## Context

See proposal.md for motivation. Gmail currently lists all messages and downloads
raw MIME directly. History does not support the full-sync `q` filter. OAuth
credentials already exist locally with callback `http://localhost:5173/gmail/oauth/callback`.
The PostgreSQL 18 test container uses localhost:29746 and its fixtures truncate
tables. No development DATABASE_URL is configured.

## Goals / Non-Goals

**Goals:** enforce a stable sender boundary before body download, retain the
existing durable jobs/cursors, and start an isolated local stack safely.

**Non-Goals:** financial parsing, sender cryptographic verification, content-based
transaction recognition, BCP until its exact address is supplied, UI filter editing,
automatic Google consent, publishing, paid services or deletion of old evidence.

## Decisions

- Use a validated JSON array `GMAIL_ALLOWED_SENDERS` in server settings, empty by
  default. Accept only plain ASCII mailbox addresses safe to embed in Gmail
  queries; normalize/lowercase/deduplicate. The user approved
  `do-not-reply@ses.binance.com` and `notificaciones@bg.com.bo`. No wildcard or
  domain-only rules. Arbitrary Gmail query text was rejected to avoid broad or
  accidentally permissive configuration.
- Add `allowed_senders` JSONB to GmailSource in a follow-up migration, not an
  edit to migration 007. Snapshot current settings on successful authorization.
  Legacy sources are blocked pending reconnection. No-filter sources fail closed
  even if reached by an old job. Reconnection reuses existing identity fencing
  and resets the full cursor; settings changes alone do not reset it.
- Full listings use `q` assembled from the saved sender list and
  `includeSpamTrash=false`. For every new full/History candidate, get
  `format=metadata`, `metadataHeaders=From` and fields restricted to id,
  labelIds and payload headers, excluding snippet/body. Validate exactly one
  From header with one mailbox, reject malformed metadata, check SPAM/TRASH,
  then request raw. A known allowed sender whose raw request returns 404 can
  still have unavailable/reviewable evidence; a metadata 404 is skipped.
  Header gating is necessary because search results alone do not prove an exact
  sender match. History can advance through irrelevant changes safely.
- Expose configured and per-source effective senders in the source listing.
  Render lists as text and warn that readonly permission remains broad, and
  permitted senders can send non-financial notices. Keep connect disabled when
  the required configuration is absent. Do not erase retained messages when
  the scope narrows; explain that retention is separate from future ingestion.
- Add `docker-compose.numa-dev.yml` with its own PostgreSQL 18 volume, loopback
  port 39747 (configurable), DB/user numa_dev and generated local password in
  an ignored env file. Use API port 39748 and a configurable Vite proxy target.
  Keep web at 5173 with strictPort because that callback is already registered.
  Only PostgreSQL is containerized; API and worker remain roles of the monolith.
- Start development services only after tests/build pass and ports are free.
  Preserve OAuth and Fernet secrets; set only missing development DB config and
  the accepted allowlist. Do not use numa_test for actual mail. Verify liveness,
  readiness, SPA and proxy without connecting a mailbox.

## Risks / Trade-offs

- Readonly authorization is mailbox-wide → explain the application-level filter;
  use minimal transient headers for History candidates and do not log/store
  excluded messages. This is not a guarantee that Google restricts the grant.
- A From field can be forged → no authentication claim, no financial mutation.
- Sender-only filtering includes other notices from approved addresses → disclose
  this limitation; later parser phases decide transaction semantics.
- Additional metadata request per new candidate → acceptable for personal usage;
  keep idempotency and do not persist a catalogue of rejected messages.
- Previously collected mail cannot be silently erased → retain immutable evidence
  and explicitly require reconnection for scope changes.
- New migration changes readiness and migration expectations → update both and
  run full PostgreSQL coverage on disposable databases.
- OAuth tests previously relied on absent configuration → explicitly disable env
  file loading in unconfigured fixtures now that real local secrets exist.

## Migration Plan

Apply the follow-up migration to development, confirm expected head/readiness,
then run API and worker with identical settings. Existing unscoped sources require
reconnection. Rollback stops worker/API first and removes the new column through
the migration; do not run the old unfiltered worker against a real mailbox.
Container shutdown keeps its volume; destructive volume removal is never part
of routine startup. Prior OpenSpec changes and retained financial data are untouched.
