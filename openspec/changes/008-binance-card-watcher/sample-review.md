# Binance Card sample review

Historical review-only sample session. On 2026-10-08 the user approved the
initial candidate implementation scope; proposal/design/specs/tasks now reflect
that approval. Missing samples below remain deferred, not retroactively obtained.

## Scope and privacy

This session implements **only the sample review authorized by the user**, not
the watcher, account mapping, conversion, or financial posting. The database
inspection ran in a PostgreSQL read-only transaction, with a bounded metadata
query (limit 1,000) and exact parsed sender check. Real amounts, merchants, dates,
recipients, identifiers, links, and raw MIME were not exported into this change.
Financial transaction/movement counts were unchanged across the inspection.

The inspection found **96** stored messages from
`do-not-reply@ses.binance.com`: **33** subjects for successful Card transactions,
**10** for failed Card transactions, and **53** other notices. All 43
success/failure subjects matched the exact UTC shape below. This is a local
point-in-time dataset, not a claim about all provider mail or future templates.

Three successful notice bodies and one failure body were selected for focused
contract verification. An earlier bounded five-template preview exposed only
allowlisted public grammar and MIME shapes, not original body values.

## Observations verified locally

| Field | Observed contract / limitation |
| --- | --- |
| Sender | Exact parsed address `do-not-reply@ses.binance.com`; sender matching is not sender authentication. |
| Success subject | `Binance Card - Transaction Successful - YYYY-MM-DD HH:MM:SS (UTC)` |
| Failure subject | `Binance Card - Transaction Failed - YYYY-MM-DD HH:MM:SS (UTC)` |
| MIME in four focused samples | Single `text/html`, UTF-8, base64, no decode issues. This does not prove multipart never occurs. |
| Success sentence | `You’ve paid <amount> <three-letter reported currency> at <merchant>. If this wasn’t you, please …` with typographic apostrophes. |
| Exact amounts | One or two fractional digits occurred in the three success samples. Preserve decimal strings/Decimal, never floats. |
| Reported currency | All **three inspected success bodies** report USD. Not a currency census of all 33 subjects. |
| Settlement | No explicit USDT token in those success bodies; no authoritative settlement amount or mapping established. |
| Event time | Subject contains an explicit UTC timestamp, used as event time per the existing design. Its underlying provider business semantics were not independently verified. |
| Notification time | Four header `Date` values had UTC offset; none preceded its subject timestamp. Retain as separate notification/check metadata. |
| Identity | All four have `Message-ID`. Retain as fallback deduplication evidence; hidden provider UUID stability remains unverified. |
| Failure | Inspected failure describes insufficient balance. It is **not** success evidence, refund evidence, or a reason to create an expense/reversal. |

Merchant extraction must not naively stop at the first period: a merchant can
contain punctuation. A future implementation must validate the whole known
sentence structure, fail closed on unexpected templates, and retain provenance.

## Prepared fixtures and verification boundaries

`api/tests/fixtures/binance_card_notice_contracts.json` contains three synthetic
success reconstructions and one redacted failure reconstruction. All private
values are invented. Minimal HTML replaces the original layout; the end of the
disclaimer is redacted. These are **contract fixtures, not full anonymized MIME
copies or authentic provider documents**. They do not establish refund, reversal,
alternate-currency, or alternate-template support.

`api/tests/test_binance_card_samples.py` constructs base64 UTF-8 HTML MIME locally
and checks it with the **existing Gmail decoder**. It also validates fixture
expectations: exact USD amount strings, separate subject/header times, unresolved
settlement/account, and no success candidate for a failed notice. These tests do
not exercise an implemented watcher, idempotent review queue, or posting guard.

## Missing evidence / next decision

- No subject among the 96 contained refund/reversal keywords. This **does not
  establish their absence** under other languages, subjects, or sources.
- Refunds, reversals, alternate reported currencies, and success-template variants
  still require real sanitized samples (or an explicit, approved scope decision
  before continuing without them).
- A Binance statement/detail showing the actual debited asset and amount, and
  authoritative account mapping with explicit configuration/review, are still
  required before any settlement can be resolved or any movement posted.
- The safe next implementation option is **USD candidates for review only**,
  with no financial movements and no USD→USDT assumption, but it requires user
  approval and a coherent scope update before implementation.

Task **8.1 remains unchecked** because its missing-evidence clauses are not
complete. Tasks 8.2–8.4 remain unchecked; no watcher behavior is claimed.

## Verification performed

- `python -m pytest -q tests/test_binance_card_samples.py tests/test_gmail.py::test_nested_mime_header_transfer_encoding_and_charset_precedence`:
  **9 passed**, no skipped tests. Existing Starlette/httpx deprecation warning
  remains non-failing. No database fixtures were invoked.
- `openspec validate 008-binance-card-watcher --strict`: valid.
- `git diff --check`: passed. Application runtime code, Gmail evidence and
  financial records were not modified. The temporary read-only inspection script
  was removed after review; no original emails were written to local fixtures.
