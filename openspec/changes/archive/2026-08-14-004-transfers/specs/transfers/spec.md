# Transfers delta

## ADDED Requirements

### Requirement: Plan-scoped Transfer root and immutable linked legs
The system MUST persist each transfer as a client-UUID, Plan-scoped Transfer
root with an immutable creation fingerprint and exactly two immutable linked
legs: one `outbound` and one `inbound`. Each leg MUST be a canonical
`transfer` Transaction with exactly one original posted Account movement. This
does not change the ledger-core invariant that one Transaction owns one
original movement: the Transfer root, rather than one Transaction, owns the
two-leg operation.

The root MUST retain both Account identities, both positive original
amounts/currencies, one common offset-aware event timestamp, rate evidence,
an applicable canonical rate source, root-only memo, provenance, and any reversal
relationship. `memo` is canonical only on the root and MUST NOT be duplicated
as an authoritative value on legs or movements. `reversal_reason` is also
root-only: it MUST be `NULL` when `reverses_transfer_id` is `NULL`, and MUST be
non-empty when the root reverses another Transfer. Each leg MUST retain the root
identity and role. A Transfer root is the canonical Transfer projection and one
grouped activity item; its two leg Transactions MUST NOT be presented as
unrelated income or expense activity.

The canonical text contract applies identically to `memo`, `reversal_reason`,
and `rate_source`. For each non-null value, Python and PostgreSQL MUST first
normalize Unicode NFC, then trim only U+0020 SPACE from the two ends. They MUST
preserve internal whitespace, non-U+0020 edge whitespace, and case exactly;
they MUST reject U+0000--U+001F, U+007F, and U+0080--U+009F; and they MUST count
the resulting Unicode code points, not bytes or graphemes. `memo` is optional:
an empty result becomes stored `NULL`, otherwise it is 1--2,000 code points.
`reversal_reason` is stored `NULL` precisely without a reversal parent and is
required, non-empty, and 1--500 code points precisely with one.

For different currencies, `rate_source` is required, non-empty, case-sensitive,
and 1--128 code points after the same canonicalization. For the same currency
it MUST be absent from the request and stored `NULL`. The response returns the
exact stored canonical memo/reversal reason (including JSON `null`) and returns
rate source only for a cross-currency root. Before any fingerprint is created,
the service MUST canonicalize these fields and place all three named persisted
values in the fingerprint: `memo`, `reversal_reason`, and `rate_source`, with a
typed `null` for each stored SQL `NULL`; it MUST NOT use a raw request value,
empty-string surrogate, or omit a null field.

#### Scenario: One root has one paired operation
- **GIVEN** a valid Plan-scoped transfer request
- **WHEN** it commits
- **THEN** exactly one Transfer root, one outbound leg Transaction, one inbound leg Transaction, two leg links, and two original movements exist, and each leg can be read as part of the same grouped root.

#### Scenario: Root-owned memo and reversal reason remain unambiguous
- **GIVEN** a Transfer with a memo and a later compensating reversal with a reason
- **WHEN** each grouped root and either direct leg are read
- **THEN** the original root alone exposes its canonical memo and a null reversal reason, the compensating root alone exposes its canonical memo and non-empty reversal reason, and neither leg is an authority for either value.

#### Scenario: API and direct SQL share one canonical text value
- **GIVEN** NFC-equivalent input, U+0020 edge spaces, internal spaces, different
  letter case, each rejected code-point range, and values at and beyond each
  field's code-point limit
- **WHEN** the same valid and invalid vectors are submitted through the API and
  through a direct SQL `INSERT`
- **THEN** both paths persist the identical NFC/U+0020-trimmed,
  internal-whitespace-preserved, case-preserved values; only an empty memo is
  stored as `NULL`; empty required fields, rejected ranges, and over-limit values
  are rejected; and the API response and fingerprint use the exact persisted
  values.

### Requirement: Atomic pair integrity and posting invariants
Transfer creation and reversal MUST execute in one PostgreSQL transaction. Both
Accounts MUST exist, be active, be distinct, and belong to the root Plan. The
outbound movement MUST be negative and the inbound movement MUST be positive.
Both original amounts MUST be non-zero exact decimal strings representable at
their respective Account currency scales; each supplied currency MUST equal its
Account currency. Same-currency absolute amounts MUST match. Transfer
Transactions and movements MUST have no Category.

The `004_transfers` persistence MUST enforce Plan-scoped foreign keys, distinct
source/destination Accounts, a unique `(plan_id, transfer_id, role)` for
`outbound|inbound`, and unique transfer-leg Transaction ownership. It MUST use
a DEFERRABLE deferred constraint trigger or equivalent commit-time mechanism.
That mechanism MUST reject a durable root unless it has exactly those two roles
and each role has exactly one matching `transfer` Transaction and original
movement with the root's Account, currency, amount, shared timestamp,
categoryless state, and required sign.

The relationship is bidirectional: every `Transaction(type=transfer)` MUST
belong to exactly one same-Plan leg; every leg MUST reference exactly such a
Transaction; and income/expense Transactions MUST never belong to a leg. Each
leg MUST own exactly one original movement in the same Plan and Transaction;
every movement classified `transfer` MUST be that unique leg movement, and its
redundant `transaction_type` MUST equal the referenced Transaction type. A
transfer movement cannot be orphaned, non-original, corrected, or mismatched to
another Transaction. The deferred mechanism MUST allow root, Transactions,
links, and movements to be inserted in one PostgreSQL transaction in a
non-final order, but MUST reject all incomplete, orphaned, or inconsistent final
states at commit. Any validation, insert, trigger, or movement failure MUST roll
back every root, leg, movement, and creation identity written by the operation.

#### Scenario: Fail after one side is prepared
- **GIVEN** an attempted transfer whose inbound leg or movement cannot be written
- **WHEN** the PostgreSQL transaction fails or the deferred pair check runs
- **THEN** neither a Transfer root, a leg, a movement, nor a durable idempotency identity remains committed.

#### Scenario: Reject an invalid pair
- **GIVEN** a request with cross-Plan, identical, unknown, archived, or currency-incompatible Accounts; a zero/nonrepresentable amount; unequal same-currency amounts; or invalid role/sign data
- **WHEN** it is submitted
- **THEN** it is rejected and no partial financial effect or Plan data disclosure occurs.

#### Scenario: Reject a direct-SQL orphan or classifier mismatch at commit
- **GIVEN** a transaction that inserts a `type: transfer` Transaction without a leg, a transfer-classified movement without a leg, an income Transaction linked as a leg, or a movement whose classifier differs from its Transaction
- **WHEN** the transaction attempts to commit
- **THEN** the deferred SQL guard rejects it and no orphan, mismatched classifier, root, leg, or financial movement is durable.

### Requirement: Migration-owned Transfer persistence and SQL immutability
Alembic revision `004_transfers` MUST follow `003_ledger_core`. It MUST create
the Transfer root and leg persistence, `NUMERIC(38,18)` original-money storage,
positive derived `NUMERIC(76,38)` rate storage,
common `TIMESTAMPTZ`, root-only memo/reversal-reason storage, Plan-scoped
composite foreign keys, root/leg/reversal indexes, unique role and leg
ownership, distinct-account and anti-self-reversal checks, and the unique direct
reversal link. It MUST evolve the prior `income|expense` Transaction and
movement type checks to allow `transfer`, make Category nullable only for
transfer rows, and enforce that income/expense retain a Category while
transfers retain none. It MUST install SQL guards for append-only roots, links,
transfer Transactions, and movements; classifier equality; bidirectional leg
ownership; exact reversal compensation; and deferred exactly-two-legs
validation. On UTF8 PostgreSQL, it MUST install immutable
`canonical_transfer_text(text)` and a `BEFORE INSERT` trigger on `transfers`
that applies the specified NFC/U+0020-only canonicalization or rejects direct
SQL input. SQL constraints MUST independently enforce canonical equality,
rejected-code-point ranges, code-point lengths, memo empty-to-null state,
reversal-reason parent/nullability, and the cross-currency-required versus
same-currency-null `rate_source` state.

The same change MUST set `api/app/db.py` exactly to
`EXPECTED_REVISION = "004_transfers"`. Runtime readiness tests MUST prove
`/health/ready` is ready at that revision and returns `503` when the database
remains at `003_ledger_core`; a migration test MUST assert that Alembic's sole
head equals this runtime constant.

#### Scenario: Upgrade all supported database starting points
- **GIVEN** an empty PostgreSQL database and a separate database at revision `003_ledger_core`
- **WHEN** each runs `alembic upgrade head` and then runs it a second time
- **THEN** `004_transfers` is applied once after `003_ledger_core`, all Transfer constraints/triggers/indexes exist, and the second upgrade is a no-op with unchanged schema and revision.

#### Scenario: Runtime accepts only the Transfer schema revision
- **GIVEN** one database upgraded to `004_transfers` and another left at
  `003_ledger_core`
- **WHEN** each is queried at `/health/ready`
- **THEN** the former returns `200`, the latter returns `503`, and Alembic's
  current head is exactly the `EXPECTED_REVISION` used by runtime.

#### Scenario: SQL refuses history rewrite
- **GIVEN** a committed Transfer root with its two legs and movements
- **WHEN** direct SQL attempts to UPDATE or DELETE the root, a link, a leg Transaction, or either movement
- **THEN** the SQL guard rejects the statement and the complete prior pair remains readable and unchanged.

### Requirement: Same- and cross-currency evidence without conversion
Same- and cross-currency transfers are in scope. For same currency, the root
MUST store equal originals, rate one at 38 fractional places, and a null
`rate_source`. For different currencies, the root MUST retain both original
amounts/currencies as canonical evidence and derive the rate as
outbound-currency units paid per one inbound-currency unit received:
`outbound_amount / inbound_amount`. The rate MUST be calculated with Python
`Decimal`, never float, under an explicit local `prec = 160` context and
quantized with `Decimal("1e-38")` and `ROUND_HALF_EVEN`. It MUST be persisted
and returned as strictly positive `NUMERIC(76,38)`.

Let the positive `NUMERIC(38,18)` amount domain have
`m = 10^-18` and `M = 10^20 - 10^-18`. The maximum ratio is
`M / m = 10^38 - 1`; the least positive ratio is
`m / M = 1 / (10^38 - 1)`, whose required 38-place representation is `10^-38`;
and its inverse is the maximum ratio. The positive `NUMERIC(76,38)` range is
`[10^-38, 10^38 - 10^-38]`, so both orientations fit. Therefore every accepted
cross-currency pair, and its exact swapped reversal pair, can be represented.
The minimum exact ratio repeats; the requirement is its mandated half-even
38-place representation, not false exact decimal termination.

Inputs MUST be validated as finite, positive, no more than 18 fractional digits,
and within `[m, M]` before division, fingerprinting, or any write; they MUST
never be rounded into that domain. The service MUST reject `InvalidOperation`,
non-finite, non-positive, zero-quantized, overflow, or underflow rate results
before write. For valid amounts the proof makes those rate failures unreachable,
but the check remains mandatory. In particular, `1e20 / 1e-18` and `1e-19 / M`
MUST return `422` as out-of-domain amount overflow/underflow, not be rounded or
written even though accepting them would respectively overflow or underflow the
rate.

The deferred SQL guard MUST independently reject a durable root whose stored
rate is not this derived result, including a same-currency rate other than one.
It MUST use an exact `NUMERIC` quotient/remainder half-even helper, not
PostgreSQL `round` alone: with integer amount units `A` and `B`, derive the
38-place scaled integer from `divmod(A * 10^38, B)`, increment on a remainder
strictly over half or an exactly-half odd quotient, and compare the resulting
`q / 10^38`. The application calculation is not the only protection against
direct SQL.

Both original amounts/currencies are canonical financial evidence. The rounded
rate is derived evidence only and MUST NOT reconstruct, replace, rescale, or
alter either original or a movement. Every Transfer retains one common
offset-aware timestamp. The system MUST NOT silently convert an amount or
automatically execute an exchange. This change MUST NOT create, resolve, or
require an exchange Quote. A later `015-exchange-rates` change MAY add an
explicit Quote reference only without rewriting this evidence, formula, or
retained originals.

#### Scenario: Cross-currency transfer
- **GIVEN** an active BOB source Account sends `100.00` BOB and an active USDT destination Account receives `10.000000` USDT in one Plan
- **WHEN** the transfer posts with rate source `manual-bank-receipt`
- **THEN** the root retains both exact originals, one timestamp, the source, and
  38-place rate `10.00000000000000000000000000000000000000` BOB per USDT; it
  posts `-100.00` BOB and `10.000000` USDT without a conversion or Quote lookup.

#### Scenario: Quantize both 38-place half-even ties
- **GIVEN** 18-decimal-scale cross-currency amounts
  `0.000000000000000001 / 40000000000000000000.000000000000000000` and
  `0.000000000000000003 / 40000000000000000000.000000000000000000`
- **WHEN** their rates are derived at 38 fractional places
- **THEN** the exact ties `2.5e-38` and `7.5e-38` persist respectively as
  `2e-38` (even lower digit) and `8e-38` (odd lower digit rounds up) under
  `ROUND_HALF_EVEN`.

#### Scenario: Retain both extreme ratio orientations
- **GIVEN** `M = 99999999999999999999.999999999999999999` and
  `m = 0.000000000000000001`
- **WHEN** one cross-currency Transfer posts `M / m` and another posts `m / M`
- **THEN** the former stores exactly `10^38 - 1`, the latter stores `1e-38`, and
  neither stored rate replaces either original.

#### Scenario: Reverse the maximum ratio
- **GIVEN** a committed cross-currency Transfer with outbound `M`, inbound `m`,
  and rate `10^38 - 1`
- **WHEN** it is reversed
- **THEN** the reversal has outbound `m`, inbound `M`, swapped currencies, and
  recalculated rate `1e-38`, rather than an inversion of the stored parent rate.

#### Scenario: Reject amount-domain overflow and underflow without writes
- **GIVEN** cross-currency requests with `1e20 / 1e-18` and `1e-19 / M`
- **WHEN** each is submitted
- **THEN** each receives `422` during amount-domain validation and no root, leg,
  movement, or idempotency identity is committed.

### Requirement: Idempotent concurrent create and reversal
`PUT /plans/{plan_id}/transfers/{transfer_id}` MUST use the client-generated
root UUID as its idempotency identity. Its canonical fingerprint MUST cover the
Plan, both Accounts, exact originals/currencies, common timestamp, canonical
persisted `rate_source`, root `memo`, and `reversal_reason` values, including
their typed null states, provenance, and derived pair facts. The initial
accepted request MUST return `201 Created`; an identical replay MUST return `200 OK`
with the durable root; a different canonical payload with the same UUID MUST
return `409 Conflict` without changing the original.

Concurrent identical creation requests MUST produce one `201` and one `200`
with exactly one root and two legs. Concurrent requests with different payloads
for the same UUID MUST produce one `201` and one `409`, never `500` or a
partial pair. The service MUST resolve a winning UUID/fingerprint before it
writes legs or movements.

The only later financial mutation MUST be idempotent reversal at
`PUT /plans/{plan_id}/transfers/{transfer_id}/reversals/{reversal_id}`. It MUST
lock the Plan-scoped source root, atomically append a new root and paired legs
that exchange the source root's Account/amount/currency facts, and link it by
`reverses_transfer_id`. The root may not reverse itself; its child must be in
the same Plan; and at most one direct child may reference a root. The reversal
has its own common offset-aware timestamp, canonical non-empty
`reversal_reason`, provenance, and rate derived from the swapped originals, not
from inversion of a rounded parent rate. Its rate source is canonical
`"reversal"` only when the swapped currencies differ and is absent/`NULL` when
they are the same. The deferred SQL guard MUST verify exact swapped
Accounts/currencies/originals and role signs against the immediate parent, so a
non-compensatory child cannot commit. It MUST not update prior history.

The reversal fingerprint MUST cover the Plan, immediate parent, reversal UUID,
derived pair, timestamp, all three named canonical persisted text values
(`memo`, `reversal_reason`, and `rate_source`, including nulls), and provenance.
Reversal UUID replay/conflict responses and fingerprint handling MUST use the
same `201`/`200`/`409` semantics. Concurrent different reversal UUIDs for one
source root MUST serialize to one `201` and one `409` with exactly one
compensating pair. A reversal root MAY itself be reversed once: each new child
compensates its immediate parent, not an arbitrary ancestor, and does not permit
a second direct reversal of an earlier root.

#### Scenario: Replay and conflict on creation
- **GIVEN** a valid Transfer UUID and canonical payload
- **WHEN** it is submitted twice and then submitted with the same UUID but a different inbound amount
- **THEN** the first response is `201`, the identical replay is `200`, the different replay is `409`, and exactly one root with two legs remains.

#### Scenario: Concurrent reversal
- **GIVEN** a posted Transfer and two concurrent reversal requests
- **WHEN** both use the same reversal UUID and payload
- **THEN** one receives `201`, one receives `200`, exactly one linked compensatory root/pair exists, and both affected balances include its two movements.

#### Scenario: Competing reversal identities
- **GIVEN** a posted unreversed Transfer
- **WHEN** two concurrent valid reversals use different reversal UUIDs
- **THEN** one receives `201`, one receives `409`, and the unique reversal link leaves only one compensating root/pair.

#### Scenario: Reject self or non-compensatory reversal data
- **GIVEN** direct SQL attempts to set a root as its own parent or create a reversal child whose Account, currency, amount, sign, or rate evidence does not exactly compensate its immediate parent
- **WHEN** the statement or deferred guard reaches commit
- **THEN** SQL rejects it, the parent is unchanged, and no invalid child pair is durable.

### Requirement: Concrete Plan-scoped Transfer API contract
The server MUST expose exactly these Transfer mutation/read routes:

- `PUT /plans/{plan_id}/transfers/{transfer_id}`;
- `GET /plans/{plan_id}/transfers`;
- `GET /plans/{plan_id}/transfers/{transfer_id}`; and
- `PUT /plans/{plan_id}/transfers/{transfer_id}/reversals/{reversal_id}`.

The create schema MUST reject unknown fields and require
`source_account_id`, `destination_account_id`, positive exact decimal-string
`outbound_amount` and `inbound_amount`, offset-aware `event_at`, and
`provenance`; it MAY accept nullable canonical `memo`. It MUST require a
non-empty canonical `rate_source` only for cross currency and reject its
presence for same currency. Currencies MUST be derived from the selected
immutable Accounts, never accepted as independently authoritative request
values. A Transfer response MUST expose the root UUID, Plan, both Accounts,
exact original amount/currency pairs, common timestamp, exact rate, root memo,
root `reversal_reason`, provenance, reversal relation, and an ordered
two-element legs array containing each leg UUID, role, Transaction UUID, and
movement UUID. It MUST expose `rate_source` only for a cross-currency root.
List responses MUST return those grouped roots, not bare legs.

The reversal schema MUST reject unknown fields and require an offset-aware
`event_at`, a canonical non-empty `reversal_reason`, and provenance; it MAY
accept nullable canonical root `memo`. It derives the compensatory Accounts,
amounts, and currencies from the source root rather than accepting client
substitutions. It derives `rate_source = "reversal"` only for a cross-currency
child and otherwise stores no source. Invalid schema, money, canonicalization,
or invariant input MUST return `422`; unknown or cross-Plan Plan/root access
MUST return `404`; UUID fingerprint conflict, already-reversed root, or a
forbidden leg correction/mutation MUST return `409` without financial effects.

#### Scenario: Observe a strict create and reversal contract
- **GIVEN** a Plan with two active distinct Accounts
- **WHEN** a client creates a Transfer and reads it, then submits its reversal with an event timestamp, reason, and provenance
- **THEN** the create returns `201` with the grouped two-leg response, the read returns the same root, the reversal returns `201` with its linked compensatory pair, and client-supplied currency/account substitution or an unknown field is rejected with `422`.

### Requirement: Immutable transfer history and forbidden single-leg mutation
Transfer roots, leg links, transfer Transactions, and transfer movements MUST
be append-only at the SQL boundary. No API MAY expose Transfer PATCH, DELETE,
leg editing, leg unlinking, or generic transfer creation through the Transaction
route. The generic Transaction correction route MUST reject every
`Transaction(type=transfer)` immediately after resolving its type and before
reading or constructing correction history, snapshots, tags, or effective
movements; this applies even if corrupted data has made the leg relation
temporarily unidentifiable. It MUST reject before writing a correction,
replacement, compensation, or canonical update.
Only the linked idempotent reversal operation may create a later financial
effect. A reversal root is subject to the same immutability and may itself be
reversed only through the same paired operation.

#### Scenario: Attempt to correct or detach one leg
- **GIVEN** a posted Transfer leg or a corrupt/unlinked Transaction whose type is `transfer`
- **WHEN** a client calls its generic Transaction correction route, attempts a PATCH/DELETE/unlink route, or SQL attempts to update/delete the root, leg, Transaction, or movement
- **THEN** correction rejects immediately with `409`, no correction snapshot/history/movement is read or appended, no partial pair is committed, and prior Transfer history remains unchanged.

### Requirement: Minimal authoritative Transfer UI
The React client MUST provide a Plan-scoped Transfer form that selects distinct
active same-Plan source/destination Accounts; accepts exact Account-scale
original amounts and one offset-aware timestamp; and gives visible validation
feedback. For different currencies it MUST require rate-source evidence and
display both originals and the `outbound / inbound` rate orientation/evidence
without claiming a conversion; for the same currency it MUST not collect or
display a rate source. It MUST display grouped Transfer details with both legs,
currencies, rate, source when applicable, timestamp, root memo, root reversal
reason, and reversal relationship, plus the idempotent reversal action with
timestamp, reason, and provenance.

The client MUST expose no edit, generic correction, unlink, or delete control
for a Transfer or leg. After a successful create or reversal it MUST refetch
authoritative grouped Transactions/activity, both affected Accounts, and active
Budget queries; it MUST not apply a local balance, budget, or FX delta.

#### Scenario: Submit and reverse through the client
- **GIVEN** a user selects active BOB and USDT Accounts
- **WHEN** the user submits exact originals, timestamp, and rate source, then reverses the grouped result
- **THEN** the UI displays the server-returned pair and evidence, offers no destructive or single-leg mutation control, and refreshes both Account balances and Budget views from server responses.

### Requirement: Transfer reporting exclusion
Transfer legs MUST update their two Account balances through their immutable
movements. They MUST be excluded from income, expense, category activity,
Ready to Assign, Assigned, Available, all budget activity,
`unconverted_by_currency`, and analytics income/expense/net totals. A
cross-currency Transfer MUST not appear as unconverted budget activity. Plan
activity and canonical projection MUST show one grouped Transfer root with both
legs and evidence rather than including either side in financial totals.

#### Scenario: Transfer reporting
- **WHEN** a linked transfer posts
- **THEN** it changes both Account balances, appears as one grouped Transfer, and changes no income, expense, category, Ready to Assign, budget, unconverted, or analytics total.
