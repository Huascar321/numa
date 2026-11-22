# Proposal

## Why

The current Gmail integration downloads the entire mailbox. Before authorizing
a real account, the user wants collection limited to known financial senders
and a local development database isolated from other projects and from tests.

## What Changes

- **BREAKING**: Gmail ingestion requires an explicit nonempty sender allowlist;
  empty/unconfigured filters never fall back to whole-mailbox ingestion.
- Filter full sync and History candidates before raw MIME download, exclude
  spam/trash, and persist the filter per connection. Existing connections without
  a filter require reconnection; retained evidence is not deleted.
- Show configured/active sender scope in the Gmail screen, explaining that the
  Google readonly grant remains mailbox-wide and sender filtering is local.
- Provide a separate local PostgreSQL 18 development container/volume on a high
  loopback-only port, run API/worker/web, and verify readiness without authorizing
  or collecting real Gmail messages automatically.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `watchers`: explicit, stable, fail-closed sender scope for Gmail ingestion.
- `architecture`: isolated local development services and collision-safe ports.

## Impact

Depends on 007-gmail, not the financial parsers in phases 008/009. Affects
`api/app/gmail`, settings, a follow-up migration/readiness revision, tests,
`web/src/GmailScreen.tsx`, Vite proxy configuration, Compose and README.
No new external dependencies, paid services, automatic financial mutation or
changes to prior change artifacts. Local credentials remain in ignored files.
