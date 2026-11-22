# Design

## Context

See proposal.md and sample-review.md. The user approved the review-only initial
scope on 2026-10-08. Gmail retains immutable decoded MIME and source identity.

## Goals / Non-Goals

**Goals:** deterministic observed USD parsing, bounded backlog/new-message
processing, durable idempotent records, plan-scoped read API and Gmail review UI.

**Non-Goals:** posting, approval/matching, account mapping, settlement resolution,
FX, refunds/reversals, other currencies/templates, mandatory AI. Missing samples
remain required for later separately approved work.

## Decisions

- A pure parser consumes the existing recursive Gmail MIME decoder output.
  Match exact sender and UTC success subject, a single UTF-8/base64 HTML leaf,
  typographic-apostrophe payment sentence and USD amount with one/two fractional
  digits. Retain amount as text, never float. Extract merchant using the known
  disclaimer delimiter, not the first period. Reject ambiguous headers/bodies,
  bad timestamps, decoding defects and unsupported currency/MIME/template.
- Each immutable Gmail message receives one versioned processing record:
  `candidate`, `needs_review`, or `ignored`. Candidates have reported facts;
  unsupported Card notices have only a reason. Failed/non-Card/wrong-sender
  notices are ignored, not expenses. No settlement/account fields can be assigned.
- Reference source evidence instead of changing it. PostgreSQL's unique message
  primary key and conflict-safe insert prevent duplicate processing. Gmail
  source/message identity is authoritative; Message-ID is retained as fallback
  evidence, not used to destructively merge distinct Gmail messages. Cross-mailbox
  semantic deduplication is deferred until provider identity is verified; same
  amount/merchant/time does not prove duplication. Hidden provider UUID stability
  remains **UNVERIFIED**.
- A bounded worker pass processes stored, unprocessed messages with row locks
  and skip-locked concurrency. New sync storage records a result in the same
  transaction as evidence; replay/backfill never overwrites existing results.
  Stored evidence remains processable after disconnect without accessing Gmail.
- Read API joins source ownership, with stable pagination and aggregate counts.
  Gmail UI displays exact strings, explicit UTC event time, source provenance and
  unresolved settlement without posting controls. Raw HTML, credentials and
  mailbox bodies are not included in list responses.

## Risks / Trade-offs

- Narrow contract → unsupported notices stay reviewable without inferred facts;
  synthetic tests do not claim real variant coverage.
- Sender spoofing → parsing is not authentication; no posting path exists.
- Immutable parser-version records → no automatic reparse/overwrite; future
  reprocessing must preserve previous evidence.
- Cross-mailbox duplicates → preserve separate evidence, never merge using only
  financial fields. No duplicate financial postings exist.

## Migration Plan

Add a review table after `007a_gmail_filter`, register metadata and advance
readiness. Run disposable PostgreSQL tests before upgrading the local development
database. Restart local API/worker only after verifying command paths. Backfill
only adds review records; verify unchanged financial counts and source evidence.
Do not drop development data for rollback.
