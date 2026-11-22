# Watchers delta

## ADDED Requirements

### Requirement: Review-only Binance Card purchases
The watcher MUST match exact sender `do-not-reply@ses.binance.com` and the observed
success subject with UTC timestamp, use recursively decoded UTF-8/base64 HTML,
and preserve exact reported USD amount, merchant, event time and source evidence.
Header `Date` MUST remain separate notification/check metadata. Every parsed
purchase MUST remain review-only with no settlement/account mapping, conversion,
approval action, transaction or ledger movement. Message-ID MUST be retained as
fallback identity evidence; hidden provider UUID stability remains UNVERIFIED.

#### Scenario: Observed USD purchase
- **WHEN** a stored notice satisfies the observed success contract
- **THEN** it produces a review-only candidate with exact reported facts and unresolved settlement.

### Requirement: Fail-closed unsupported notices
The watcher MUST NOT infer expenses from failed transactions or unrelated
notices. Unsupported Card subjects, currencies, MIME, malformed/ambiguous payment
sentences, headers, or timestamps MUST require review without invented facts.
Refund, reversal, alternate-currency/template and settlement resolution support
MUST remain deferred until samples and a separately approved change exist.

#### Scenario: Failed transaction
- **WHEN** a sender-matched notice has the exact failed-transaction subject
- **THEN** it is ignored and creates neither a purchase candidate nor a movement.

#### Scenario: Unsupported currency or template
- **WHEN** a Card notice is not an unambiguous observed USD success
- **THEN** the record requires review with a reason and no inferred amount, account or settlement.

### Requirement: Durable idempotent review evidence
The watcher MUST preserve immutable Gmail evidence and create at most one
processing record per stored source-message, including backfill, retries and
concurrent workers. Separate Gmail messages MUST NOT be destructively merged
using unverified identities or coincident financial fields.

#### Scenario: Concurrent replay and backfill
- **WHEN** multiple passes encounter the same stored Gmail message
- **THEN** one processing record exists and source evidence and finances are unchanged.

### Requirement: Plan-isolated review access
The API and Gmail UI MUST provide read-only, paginated plan-owned review records,
exact amount strings, source provenance and explicit unresolved-settlement status.
They MUST NOT expose posting/approval actions or render raw source HTML.

#### Scenario: Other Plan
- **WHEN** a caller lists a different Plan's reviews
- **THEN** no source or candidate from the original Plan is returned.

## Evidence

See sample-review.md for observed contract and privacy limits. On 2026-10-08 the
user approved proceeding with only review candidates while missing refund,
reversal, alternate-currency/template and USDT evidence remain explicit deferrals.
