# Design

## Contract and exact calculation

The client supplies a reconciliation-session UUID, an exact plain decimal-string
`statement_balance`, the Account currency code, and `statement_at`. The decimal
representation is bounded to the ledger `NUMERIC(38,18)` domain: optional minus
sign, 1-20 integer digits, and at most 18 fractional digits. Exponent notation,
JSON numbers, longer representations, non-finite values, and rounding are
rejected before decimal parsing. The currency MUST equal the Account's immutable
currency and the amount MUST be exactly representable at its registered scale.
`statement_at` MUST be a string carrying `Z` or `+00:00` and is persisted as
`TIMESTAMPTZ` normalized to UTC.

The Plan-scoped as-of projection is the exact sum of immutable posted movements
for the selected `(plan_id, account_id, currency_code)` whose `effective_at <=
statement_at`. The single discrepancy orientation is:

`discrepancy = statement_balance - derived_balance`

All persisted monetary evidence uses PostgreSQL `NUMERIC` and all API amounts
are scale-formatted strings. Python and JSON floats are never accepted.

## Movement serialization

Confirmation takes a PostgreSQL `SELECT FOR UPDATE` lock on the selected Account
before calculating the as-of balance and holds it through commit. Every current
service path that can insert an Account movement uses the same Account-row lock:
manual Transactions, correction compensation/replacement pairs, Transfers,
Transfer reversals, and reconciliation adjustments. Multi-Account operations
lock unique Account UUIDs in ascending deterministic order. This makes a
movement writer that already owns the lock commit before reconciliation reads,
while a later writer serializes after the confirmed reconciliation, and avoids
opposite-direction Transfer deadlocks.

## Preview and policy

`POST /plans/{plan_id}/accounts/{account_id}/reconciliations/{session_id}/preview`
performs only reads and returns the comparison, effective policy, exact
tolerance, and whether explicit warning acceptance is required. It creates no
session, Transaction, movement, or idempotency row.

Server-only configuration is deliberately small:

- `RECONCILIATION_POLICY` is exactly `block|warn` and defaults to `block`.
- `RECONCILIATION_TOLERANCE_ATOMS` is a non-negative integer and defaults to
  `0`. At request time it is converted exactly to the selected Account's
  smallest currency units (`atoms * 10^-decimal_places`), so configuration
  cannot introduce an invalid fractional scale.

If `abs(discrepancy) <= tolerance`, either policy permits confirmation without a
warning acceptance. Above tolerance, `block` rejects confirmation and `warn`
requires `warning_accepted: true`. Preview reports that condition but never
confirms it implicitly.

## Atomic confirmation, idempotency, and history

`PUT /plans/{plan_id}/accounts/{account_id}/reconciliations/{session_id}` accepts
the same statement facts plus strict boolean `warning_accepted`. It recomputes
the authoritative as-of balance inside one database transaction, applies the
configured policy, and resolves the client UUID before any adjustment effect.
The immutable creation fingerprint includes Plan, Account, statement facts, and
warning acceptance. The winner returns `201`; a matching sequential or
concurrent retry returns the same persisted result with `200`; a UUID reuse with
different facts returns `409`. SQL uniqueness and the transaction prevent more
than one session, adjustment Transaction, or adjustment movement for that UUID.

Every successful confirmation persists an immutable reconciliation session with
statement, derived, discrepancy, policy, tolerance, warning acceptance, and
confirmation time. A zero discrepancy is an auditable confirmation with no
Transaction or movement. A non-zero allowed discrepancy posts exactly one
`reconciliation_adjustment` Transaction and one original movement at
`statement_at`, signed by the discrepancy. Thus a positive discrepancy raises
the Account balance and a negative discrepancy lowers it.

The adjustment has no Category, is excluded from all income, expense, Ready to
Assign, envelope, unconverted, and transfer projections, and is protected from
generic correction, update, and deletion. Deferred SQL integrity checks enforce
the session/Transaction/movement relationship, exact facts, policy evidence,
Account ownership/status, and one-adjustment limit; append-only triggers protect
the session and adjustment even when the service is bypassed.

An archived Account remains eligible for historical preview. It may also retain
a zero-discrepancy confirmation because that writes no movement. A non-zero
confirmation is rejected because it would post an adjustment to an archived
Account. A retry of an already confirmed session returns its original result
even if the Account was archived later.

`GET /plans/{plan_id}/accounts/{account_id}/reconciliations` returns immutable
confirmation history, including optional adjustment identities. All reads and
writes predicate on both Plan and Account. The web flow previews first, displays
policy and warning state, requires an explicit confirm action, then invalidates
and refetches reconciliation history, Accounts, Transactions, and active Budget
queries as authoritative server state.
