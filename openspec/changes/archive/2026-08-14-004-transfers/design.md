# Design

## Context and decision

`003_ledger_core` makes one canonical Transaction own exactly one original
posted Account movement. A transfer cannot use one Transaction with two
movements without breaking that invariant. Therefore, a Transfer is a
Plan-scoped root operation and owns exactly two canonical Transaction legs:

- the `outbound` leg is a `transfer` Transaction with one negative original
  posted movement in the source Account; and
- the `inbound` leg is a `transfer` Transaction with one positive original
  posted movement in the destination Account.

The root is the canonical projection and activity item for the operation. The
leg Transactions remain immutable audit records and retain `transfer_id` and
role for direct reads. Plan activity and the Transaction list collapse the two
legs into the single root Transfer representation, so they are never presented
as unrelated income or expense records. This preserves the ledger-core
one-Transaction/one-original-movement rule while making both sides explicit.

## Persistence and migration

Alembic revision `004_transfers` follows `003_ledger_core`. It creates:

- `transfers`: client UUID root, `plan_id`, source and destination Account
  identities, outbound and inbound positive original amounts/currencies,
  common offset-aware `event_at`, derived `NUMERIC(76,38)` exchange-rate
  evidence, canonical cross-currency `rate_source`, root-only nullable `memo`, root-only
  nullable `reversal_reason`, provenance, immutable creation fingerprint,
  creation timestamp, and nullable `reverses_transfer_id`;
- `transfer_legs`: `plan_id`, `transfer_id`, immutable leg Transaction UUID,
  and role `outbound|inbound`; and
- Plan-scoped composite foreign keys from roots and legs to Accounts,
  Transactions, and the reversed root. The root has `CHECK
  (source_account_id <> destination_account_id)` and `CHECK (id <>
  reverses_transfer_id OR reverses_transfer_id IS NULL)`. A unique `(plan_id,
  transfer_id, role)` constraint, unique `(plan_id, transaction_id)`, and
  unique non-null `(plan_id, reverses_transfer_id)` prevent duplicate roles, a
  Transaction belonging to two transfers, and more than one direct reversal of
  a root.

The root's `event_at` is the operation instant and its creation timestamp is
the root audit time; it has no mutable `updated_at`. Each leg uses the existing
Transaction `id`, `event_at` (required to equal root `event_at`),
`created_at`, and immutable initial `updated_at`. Its sole movement has its own
movement `id`, `effective_at` (also required to equal root `event_at`), and
`posted_at`; the movement's signed amount is the only signed monetary value.
Root outbound/inbound amounts and leg Transaction amounts are positive original
amounts, while the root rate is derived evidence only. These identities and
timestamps are returned through the grouped root/leg response without changing
their table ownership.

`memo` is authoritative only on the Transfer root and is never copied to either
leg Transaction or movement as an authoritative Transfer field.
`reversal_reason` is likewise root-only. Their canonicalization, nullability,
fingerprint, and direct-SQL enforcement contract is defined below. The root has
checks that require a null `reversal_reason` without a reversal parent and a
non-empty canonical one with a parent.

The migration extends `transactions.type` and the redundant
`posted_account_movements.transaction_type` checks to include `transfer`. The
movement classifier remains persisted for projection/query efficiency and audit,
but is never independently authoritative: the deferred integrity mechanism
requires it to equal the referenced Transaction's `type` on every movement.
It makes `category_id` nullable in both tables and adds conditional checks:
`income` and `expense` require a category; `transfer` requires no category.
Transfer legs always use `movement_kind = original`, `correction_id IS NULL`,
and `correction_sequence = 0`; generic correction rows and
compensation/replacement movements are forbidden for every
`Transaction(type=transfer)`, whether or not a corrupt writer managed to link
it first.

A PostgreSQL `DEFERRABLE INITIALLY DEFERRED` constraint trigger, or an
equivalent commit-time mechanism, runs after INSERT, UPDATE, or DELETE of a
root, leg, Transaction, or movement. It evaluates final transaction state at
commit, so a service may insert the root, both Transactions, both links, and
both movements in any safe order in one PostgreSQL transaction. It then rejects
all of the following durable states:

- a Transfer without exactly two legs, one `outbound` and one `inbound`;
- a `transfer_leg` whose same-Plan Transaction is absent or has a type other
  than `transfer`, or an income/expense Transaction that belongs to a leg;
- a `Transaction(type=transfer)` without exactly one leg, including an orphan
  created by direct SQL;
- a leg without exactly one original movement, or a transfer-classified
  movement without exactly one corresponding leg Transaction in the same Plan;
- any movement whose `transaction_type` differs from its referenced
  Transaction's type, including a transfer classifier on a non-transfer
  Transaction or a non-transfer classifier on a leg movement;
- a leg movement that is not original, has a correction link/positive correction
  sequence, has a Category, or has a Plan/Transaction different from its leg;
- a leg Transaction or its only movement whose Account, currency, positive
  absolute amount, or time (`Transaction.event_at` and
  `movement.effective_at`) differs from the root's common event facts; and
- a root whose stored rate is not the required Decimal-derived,
  round-half-even `outbound_amount / inbound_amount` result (or exactly one for
  same currency), whose rate source is not canonical or is present for a
  same-currency root, or whose rate cannot fit positive `NUMERIC(76,38)`; and
- an outbound movement that is not negative, an inbound movement that is not
  positive, unequal same-currency originals, or a root whose Accounts are the
  same.

Thus no root, leg, transfer Transaction, or transfer-classified movement can be
partial, orphaned, or inconsistently classified at commit, even when a writer
bypasses the application service.

SQL append-only triggers reject UPDATE and DELETE of `transfers`,
`transfer_legs`, transfer Transactions, and all posted movements. The existing
movement append-only guard is retained and extended for the transfer checks. An
immediate correction guard reads only the locked Transaction type and rejects a
generic correction for `type = transfer` before reading correction history,
snapshots, tags, or an effective movement; a SQL `BEFORE INSERT` guard rejects
the corresponding direct correction row. No transfer-leg unlinking relation or
destructive route exists.

The migration and runtime revision move together: it updates
`api/app/db.py` to set `EXPECTED_REVISION = "004_transfers"`. The migration
suite proves a clean-database upgrade, upgrade from `003_ledger_core`, and a
second `upgrade head` no-op. It also proves that `/health/ready` is `200` only
at `004_transfers`, remains `503` at `003_ledger_core`, and that Alembic's sole
head equals the runtime `EXPECTED_REVISION` constant.

## Canonical root text contract

This is the single contract for `memo`, `reversal_reason`, and `rate_source`.
It is deliberately defined in Unicode code points rather than by locale or
ambiguous "whitespace"/"control" classes. The database cluster for this change
MUST use `UTF8` server encoding, which the migration asserts before installing
the canonicalization function.

For a non-null supplied string, Python and PostgreSQL perform exactly this
ordered algorithm:

1. Normalize to Unicode NFC.
2. Trim from each end only U+0020 SPACE. No other code point is trimmed.
3. Preserve every remaining code point exactly: internal whitespace is not
   collapsed or transformed, U+0020 internal spaces are preserved, non-U+0020
   whitespace at either end is preserved, and case is not folded.
4. Reject a result containing a code point in U+0000--U+001F, U+007F, or
   U+0080--U+009F. (PostgreSQL `text` cannot receive U+0000, but Python rejects
   it too so the contract is identical at the API boundary.)
5. Measure the resulting value in Unicode code points, not bytes or grapheme
   clusters. In Python this is `len`; in PostgreSQL UTF8 it is `char_length`.

The field rules after that algorithm are:

| Field | API/persistence rule | Stored, returned, and fingerprinted value |
| --- | --- | --- |
| `memo` | Optional. A canonical empty result becomes `NULL`; otherwise it is 1--2,000 code points. | `NULL` or the exact canonical string. |
| `reversal_reason` | Must be absent/`NULL` when `reverses_transfer_id` is `NULL`; it is required and must be 1--500 code points when that parent is non-null. An empty canonical result is rejected. | `NULL` or the exact canonical string. |
| `rate_source` | For different currencies it is required and must be 1--128 code points; an empty canonical result is rejected. For the same currency it MUST be absent from the request and is stored as `NULL`. | The exact canonical string for cross-currency; `NULL` for same-currency. |

The API response returns the exact stored canonical `memo` and
`reversal_reason` (including JSON `null`). It returns `rate_source` only for a
cross-currency root; a same-currency root has no `rate_source` response member.
The canonical fingerprint is constructed only after this algorithm and contains
three named values, `memo`, `reversal_reason`, and `rate_source`, exactly as
they are persisted; each SQL `NULL` is represented by the typed JSON `null`
value, not an omitted field, empty string, or raw request value. Thus all three
fields participate in both create and reversal fingerprints, including their
required null states.

Python uses `unicodedata.normalize("NFC", value)`, `strip(" ")` (never bare
`strip()`), an `ord()` range check, and the stated `len` bounds before it
constructs that fingerprint. PostgreSQL installs immutable
`canonical_transfer_text(text)` and a `BEFORE INSERT` trigger on `transfers`.
The function applies `normalize(value, NFC)`, `btrim(value, U&'\0020')`, and
an `ascii(substring(...))` code-point loop that rejects exactly the ranges
above. The trigger assigns the canonical values to `NEW.memo`,
`NEW.reversal_reason`, and `NEW.rate_source`; it turns only an empty memo into
`NULL`, rejects an empty reason/source, and rejects a non-null source when the
currencies are equal. It therefore canonicalizes or rejects a direct SQL
INSERT before it can persist a different value.

Constraints duplicate the durable boundary: each non-null text field must
equal `canonical_transfer_text(field)`, satisfy its `char_length` bounds, and
contain no rejected range; the reversal-parent check enforces the exact
`reversal_reason` nullability; and the currency-pair check requires
`rate_source IS NULL` exactly for same currency and a non-null canonical source
exactly for cross currency. The deferred root guard uses those persisted values
when validating a root. SQL-direct tests and API tests run the same NFC,
U+0020-edge-space, internal-whitespace, case, rejected-range, empty-result,
and boundary-length vectors and assert equal persisted values and fingerprints.

## Amounts and FX evidence

All request amounts are positive exact decimal strings, non-zero, and must fit
the immutable currency scale of their selected Accounts. Both Accounts must be
different, active, and owned by the root Plan. The root's outbound/inbound
currency values must equal those Accounts' currencies. No float, rounding of
amounts, account substitution, cross-Plan reference, or posting to an archived
Account is accepted.

For the same currency, outbound and inbound absolute amounts are identical and
the persisted rate is exactly `1.00000000000000000000000000000000000000`.
For different currencies, both original amounts remain canonical evidence; the
server derives and stores the rate as **outbound-currency units paid per one
inbound-currency unit received**:

`rate = outbound_amount / inbound_amount`

### FX domain proof and derivation

The amount domain is positive `NUMERIC(38,18)`, so its least value is
`m = 10^-18` and its greatest value is
`M = 10^20 - 10^-18 = 99999999999999999999.999999999999999999`. Let
`A = outbound_amount / m` and `B = inbound_amount / m`; after amount validation
they are integers in `[1, 10^38 - 1]` and `rate = A / B`. Consequently:

- the greatest possible ratio is `M / m = 10^38 - 1`;
- the least positive ratio is `m / M = 1 / (10^38 - 1)`; and
- its inverse is exactly the greatest ratio.

Positive `NUMERIC(76,38)` values range from `10^-38` through
`10^38 - 10^-38`. Therefore `10^38 - 1` fits, and the least exact ratio, which
is greater than `10^-38`, has the required 38-place half-even representation
`10^-38`; its inverse fits exactly. The minimum ratio has a repeating decimal,
so this statement deliberately proves fit of its mandated 38-place stored
representation, not an impossible claim that every rational ratio terminates.
`NUMERIC(76,38)` therefore covers both orientations for every valid amount
pair; no wider PostgreSQL precision/scale is needed.

The service validates the two inputs against that amount domain before division:
they must be finite, positive, at most `M`, and have no more than 18 fractional
digits, without amount rounding. It then uses Python `Decimal`, never float,
inside an explicit local context with `prec = 160`, calculates the finite ratio,
and quantizes it with `Decimal("1e-38")` and `ROUND_HALF_EVEN`. The context is
substantially greater than the 76 stored digits. It is also sufficient to decide
every boundary: a non-tie amount ratio is at least
`1 / (2 * 10^38 * B) > 0.5e-76` away from a 38-place half, while a 160-digit
division at the largest possible magnitude has error below `0.5e-122`; an exact
half terminates within 77 significant digits and is exact in that context.

Before writing anything, the service rejects `InvalidOperation`, non-finite or
non-positive results, a quantized zero, or a value outside positive
`NUMERIC(76,38)`. Valid amount-domain inputs cannot reach either rate failure:
the proof above bounds their quantized result in `[10^-38, 10^38 - 1]`. The
check remains mandatory as a defensive pre-write boundary. A supplied amount
outside the domain is also rejected before rate derivation, fingerprinting, or
any root/leg/movement/idempotency write: `1e20 / 1e-18` is an amount overflow
that would otherwise produce rate `1e38`, and
`1e-19 / M` is an amount underflow that would otherwise quantize to zero.
Neither value is rounded into the amount domain.

The deferred SQL guard independently invokes an exact `NUMERIC` quotient and
remainder helper, rather than PostgreSQL `round` alone, to reproduce this rule
for direct SQL. It computes `P = A * 10^38`, `q, remainder = divmod(P, B)`, then
increments `q` iff `2 * remainder > B` or `2 * remainder = B` and `q` is odd.
It persists/compares `q / 10^38`, requires `q > 0`, and verifies the
`NUMERIC(76,38)` bound. This is the same half-even result as `Decimal`, uses no
float, and avoids PostgreSQL numeric's different tie rule.

The following normative 38-place vectors use positive 18-decimal-scale amounts
and replace all former 18-place rate vectors:

- **Lower half-even tie:** outbound `0.000000000000000001` / inbound
  `40000000000000000000.000000000000000000` is exactly `2.5e-38` and stores
  `2e-38`, because the lower scaled integer `2` is even.
- **Upper half-even tie:** outbound `0.000000000000000003` / the same inbound
  amount is exactly `7.5e-38` and stores `8e-38`, because the lower scaled
  integer `7` is odd.
- **Maximum orientation:** outbound `M` / inbound `m` stores exactly
  `10^38 - 1` at scale 38.
- **Minimum orientation:** outbound `m` / inbound `M` has exact ratio
  `1 / (10^38 - 1)` and stores `1e-38` at scale 38.
- **Reversal of the maximum:** reversing the maximum-orientation root swaps the
  exact originals and currencies, recalculates from `m / M`, and stores
  `1e-38`; it never inverts the parent's stored rate.
- **Out-of-domain amount rejection:** the `1e20 / 1e-18` and `1e-19 / M`
  vectors above return `422` before writes, respectively exercising amount
  overflow and amount underflow that would create a rate overflow or underflow
  if accepted.

The originals are the only canonical financial evidence and the only amounts
used by movements, balances, and reversal. The rate is derived evidence only:
its 38-place rounding is never used to reconstruct, replace, rescale, or alter
either original amount. Since every accepted cross-currency pair and its
swapped pair are in the proved domain, every accepted cross-currency Transfer
can be reversed. `event_at` is one common offset-aware instant on both legs.
The change neither silently converts values nor performs exchange execution. It
neither creates nor looks up a Quote: `015-exchange-rates` may later add an
explicit quote reference only with a new migration and without changing this
retained evidence or rate formula.

## Create, idempotency, and concurrency

`PUT /plans/{plan_id}/transfers/{transfer_id}` uses a client-generated UUID as
the root identity. Its canonical fingerprint contains the Plan, both Accounts,
both exact originals/currencies, common timestamp, and the three named
canonical persisted text values `memo`, `reversal_reason`, and `rate_source`
(including their typed null values), plus provenance and all facts that form the
two legs. In one PostgreSQL transaction the service resolves the UUID before
creating any leg effect, then inserts the root, two leg Transactions, two leg
links, and their two original movements. It returns `201 Created` for the
winner, `200 OK` for an identical replay, and `409 Conflict` if the UUID
identifies a different canonical payload. A failed validation, insert, trigger,
or movement write rolls back the root, legs, movements, and idempotency identity
together.

The unique root identity plus `INSERT ... ON CONFLICT DO NOTHING` followed by a
durable-row fingerprint read makes concurrent identical creates yield exactly
one root, two legs, and two movements with one `201` and one `200`. Concurrent
different payloads with the same UUID yield one `201` and one `409`, never a
partial pair or `500`.

## Reversal and forbidden mutations

The only later financial mutation is
`PUT /plans/{plan_id}/transfers/{transfer_id}/reversals/{reversal_id}`. It locks
the Plan-scoped source root before inspecting reversal state. `reversal_id` is
the client UUID and root ID of a new Transfer whose outbound facts equal the
source root's inbound facts and whose inbound facts equal its outbound facts.
It has its own required common offset-aware reversal timestamp and root-only
required `reversal_reason`. When the swapped currencies differ it stores the
canonical `rate_source = "reversal"`; when they are the same its `rate_source`
is absent and stored `NULL`. It derives its rate from the swapped originals at
the same precision and links `reverses_transfer_id` to the source root. The
resulting pair compensates both Account balances without changing any prior row.

The deferred SQL guard verifies every non-null reversal link against its
immediate parent: child source/destination Accounts and currencies are swapped;
child outbound/inbound originals equal the parent's inbound/outbound originals
exactly; its two movement signs satisfy the normal role rules; its stored rate
is recalculated from those swapped originals rather than by inverting the
parent's rounded rate; and its `rate_source` is exactly `reversal` only for a
cross-currency child and `NULL` only for a same-currency child. The Plan-scoped
self foreign key, anti-self-reversal check, and unique direct-parent reference
make the relationship same-Plan, non-reflexive, and one-to-one in the child
direction. The guard never updates either parent or ancestor.

The reversal fingerprint includes the Plan, source Transfer, reversal UUID,
derived pair, timestamp, and all three named canonical persisted text values:
`memo`, `reversal_reason`, and `rate_source`, including their typed null
states, plus provenance. It has the same single
PostgreSQL transaction and `201`/`200`/`409` behavior as creation. Concurrent
identical reversal requests yield one `201` and one `200`; concurrent different
reversal UUIDs for the same source root serialize on that root, yield one
`201` and one `409`, and leave one reversal pair. A Transfer may have at most
one direct reversal; a reversal root is itself immutable and may be reversed by
the same rule if still unreversed. This is an immediate-parent chain: reversing
reversal `B` of root `A` creates `C` that compensates `B` exactly (and
consequently reintroduces `A`'s original economic facts). It does not create a
second direct reversal of `A`.

There is no Transfer PATCH, DELETE, leg route, generic transfer creation route,
or leg unlink route. The generic Transaction correction endpoint rejects any
`Transaction(type=transfer)` immediately after its type lookup, before reading
or constructing correction history/snapshots, even if corrupt data has made its
leg relation temporarily unavailable. Editing, deleting, correcting, or
detaching one side is therefore impossible through both API and SQL guards.

## Projections and client behavior

Both posted movements participate in each affected Account's exact derived
balance. Transfer roots and grouped activity expose both legs, their Accounts,
exact originals, shared time, rate evidence, and reversal relation. They are
never classified as income, expense, category activity, Ready to Assign,
budget activity, `unconverted_by_currency`, or analytics income/expense.
Budget and reporting selectors explicitly match `income` or `expense`; none may
treat every non-income classifier as expense. In particular,
`_unconverted_summary` adds an expense only when
`movement.transaction_type = 'expense'`. The SQL classifier-equality guard
rejects mismatches before any projection can observe them.

The web client provides a Plan-scoped transfer form with active, distinct
source/destination Account selection; exact scale-aware amount feedback; a
common timestamp; rate-source evidence required only for cross currency; and an
explicit cross-currency rate/evidence preview. It omits rate source for same
currency. It shows a grouped Transfer detail and a reversal action, but no edit,
correction, unlink, or delete action. After a create or reversal, it invalidates
and refetches authoritative Plan Transactions/activity, both affected Account
queries, and active Budget queries; it never applies local balance or budget
