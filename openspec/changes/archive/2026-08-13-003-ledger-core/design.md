# Design

## Context

`002_accounts` established Plans and Accounts with an empty-set derived
balance. This change introduces the first records that can affect that balance
while preserving Plan isolation, exact money, retry safety, and a complete
financial audit trail.

## Goals

- Post manual income and expense Transactions with exact money in one
  PostgreSQL transaction.
- Create a Plan-local category taxonomy, including one immutable `Pendientes`
  Category for every Plan, and Plan-local Tags.
- Derive Account balances exclusively from immutable posted movements.
- Make all transaction corrections reviewable and financially compensating,
  rather than silently rewriting prior ledger effects.
- Provide the monthly envelope baseline in the Plan's own IANA timezone,
  without silently converting currencies or implementing later budget-engine
  behavior.

## Non-Goals

- Transfers belong to `004-transfers`.
- Rollover, overspending policy between months, goals/targets, and special
  credit-card budget automation belong to `005-budget-engine`.
- Reconciliation preview and creation of `reconciliation_adjustment` belong to
  `006-reconciliation`.
- `cleared`, destructive deletion, binary photo storage, currency conversion,
  final navigation, and advanced visual design are not introduced.

## Decisions

### Migration and exact persistence

Alembic revision `003_ledger_core` follows `002_accounts`. It adds a non-null,
immutable `budget_timezone` IANA name to `plans`; all existing Plans receive
the explicit initial assumption `America/La_Paz`. New Plan creation requires
an IANA timezone and atomically creates its protected `Pendientes` Category.

The revision creates Plan-scoped `category_groups`, `categories`, `tags`,
`transactions`, `posted_account_movements`, immutable
`transaction_corrections`, append-only Transaction--Tag association history,
and `monthly_budget_assignments`. Every money column is PostgreSQL `NUMERIC`
or an integer atomic-unit column; this change uses `NUMERIC` and the shared
exact-money boundary. `REAL`, `DOUBLE PRECISION`, Python floats, and JSON
floating-point money are invalid.

Every Plan-owned relation persists `plan_id`. Composite foreign keys and
Plan-scoped lookup predicates enforce that Accounts, Category Groups,
Categories, Tags, Transactions, movement snapshots, Transaction--Tag links,
and budget assignments cannot refer across Plans. Categories have a direct
Plan owner and an optional Category Group; a group, when present, must belong
to the same Plan. This permits the protected `Pendientes` Category to exist
without inventing a system group.

`categories.is_pending` identifies the protected Category. Database and
service invariants ensure exactly one active `Pendientes` Category per Plan,
with that exact name. The upgrade backfills it for every existing Plan. A
protected Category cannot be renamed, archived, deleted, moved, or replaced.
Other Categories, Groups, and Tags use one-way archive lifecycle operations;
their historical references remain readable. No resource in this change has a
DELETE route.

### Canonical transactions and posting

`transactions` stores the current canonical projection and immutable creation
facts: client UUID and creation fingerprint, Plan and Account, type, positive
exact amount and currency, timezone-aware event timestamp, Category, merchant,
memo, optional opaque photo reference, optional location, source, source
metadata, provenance, and timestamps. Source for the public operation is
`manual`; original source metadata and provenance are retained, not replaced
by a human correction. Photos are only opaque references; no blob column,
upload endpoint, or binary storage is added.

The public create operation accepts only `income` and `expense`. It requires a
positive decimal-string amount representable at the Account currency scale and
requires the supplied currency to equal that Account's immutable currency. It
requires an offset-aware timestamp. Omitted Category resolves to the
Plan-local `Pendientes` Category. Supplied Categories and Tags must be active
and owned by the same Plan. Archived Accounts remain readable but reject new
postings. `reconciliation_adjustment` is a reserved type for
`006-reconciliation`; `transfer` is not introduced until `004-transfers`, and
there is no `cleared` field.

In one PostgreSQL transaction, a successful create writes the canonical
Transaction, its current Tag links, and exactly one posted movement. The
movement stores a signed exact amount and a snapshot of its financial facts:
Plan, Account, currency, transaction type, effective timestamp, Category, and
descriptive facts required for audit. Income writes a positive movement;
expense writes a negative movement. The Account balance projection is always
`SUM(posted_account_movements.signed_amount)` for that Account and currency.
No Account, Transaction, or projection table stores an editable running or
opening balance.

Client UUIDs in creation paths are idempotency identities. The first accepted
canonical request returns `201`; an identical replay returns `200` with the
current resource; reuse with a different canonical fingerprint returns `409`
without a second record or mutation. This applies to taxonomy records,
Transactions, corrections, and monthly assignments.

### Corrections and immutable financial history

A correction is an immutable, client-UUID-identified event that records the
prior snapshot, requested replacement snapshot, provenance, and timestamps.
It atomically updates the canonical current Transaction projection and appends
ledger effects; it never edits or deletes an existing movement. The correction
first executes `SELECT ... FOR UPDATE` on the Plan-scoped Transaction and only
then reads its snapshot, current Tag state, or effective movement. It assigns a
monotonic `correction_sequence` (`BIGINT`, starting at 1), enforced unique for
`(plan_id, transaction_id, correction_sequence)`. The original movement is the
sequence-zero baseline; the effective movement is the replacement linked to the
greatest committed correction sequence. `created_at`, `posted_at`, and UUID
ordering are never used to choose the effective movement. The sequence is
exposed in correction history and retained on every correction movement for
audit/debugging. The correction then selects the currently effective movement
and appends:

1. a compensating movement with the opposite signed amount and the old Account,
   Category, timestamp, and descriptive snapshot; and
2. a replacement movement with the corrected signed amount and corrected
   snapshot.

For an amount correction this changes the net amount; for an Account correction
it removes the effect from the former Account and posts it to the replacement
Account; for Category or timestamp correction it removes old-period/category
activity and posts corrected activity. Merchant and memo corrections still
append the compensating/replacement pair so their financial snapshot remains
auditable while their net balance and activity stay unchanged. Reversals use
the prior effective timestamp and replacements use the corrected timestamp,
while each stores its actual posting time separately. Tag association changes,
when corrected, are retained as append-only link history. Corrections cannot
destroy a Transaction or any prior movement.

Two concurrent corrections for one Transaction therefore wait on the same row
lock and execute as a sequential chain. The second correction reads the first
correction's canonical projection and effective replacement, compensates that
replacement exactly, and receives the next sequence. A retry with the same
client UUID is resolved after the lock against the immutable fingerprint; an
identical request returns the existing correction and a different payload
returns `409` without ledger effects.

### PostgreSQL idempotency under concurrency

All client-UUID creation paths (Category Groups, Categories, Tags,
Transactions, corrections, and monthly assignments) use one PostgreSQL
transaction and `INSERT ... ON CONFLICT DO NOTHING` against the UUID identity,
followed by a read of the row that won the race. PostgreSQL waits for an
uncommitted conflicting insert before the losing request reads the durable row.
The winner returns `201`; an identical loser returns `200`; a different
fingerprint returns `409`. No movement, tag link, correction, or assignment
effect is written before the UUID result is resolved, so a conflict cannot leave
partial durable state.

### Monthly budgeting baseline

A `monthly_budget_assignments` record is an immutable, client-UUID-idempotent
Plan/Category/month/amount event. Its signed exact amount may be positive or
negative. A correction to an allocation is represented by another assignment,
not an update or deletion. The month key is `YYYY-MM`; its interval is computed
as the start of that local month through the start of the next local month in
the Plan's `budget_timezone`, then compared against timezone-aware movement
timestamps. The server timezone never determines membership.

For a requested Plan month, using only posted movements in the Plan's budget
currency:

- `Ready to Assign = income movements for the month - all assignments for the month`.
- `Assigned(category) = assignments for that Category and month`.
- `Activity(category) = expense movements for that Category and month`, signed
  negative.
- `Available(category) = Assigned(category) + Activity(category)`.

Transactions in a different Account currency still post to and affect that
Account balance. They are not converted and are not included in the equations.
Monthly summary and Category envelope responses instead expose them as
`unconverted_by_currency`, with separate exact values and transaction IDs per
currency so unlike currencies are never aggregated. No rollover, cross-month
overspending rule, goal/target, or credit-card automation is inferred.

### HTTP API and UI boundary

All routes are Plan-scoped. PUT creation routes place client UUIDs in their
resource paths; GET reads current and historical data; PATCH performs only
allowed non-financial taxonomy updates; POST archive routes are one-way. The
transaction correction route is a PUT creation route because it creates an
immutable correction event. The Account resource and its dedicated balance
route expose the server-derived balance as an exact decimal string.

The minimal React client uses authoritative query results to manage Category
Groups, Categories, and Tags; submit manual income/expense forms; list, view,
and correct Transactions; and show a basic monthly summary and Category
envelopes. It visibly separates `unconverted` amounts by currency. It does not
add final navigation, advanced design, transfer UX, reconciliation UX, or photo
upload/storage.

After a successful posting or correction the client invalidates and refetches
the Plan's Transactions, Accounts (whose balances are derived from movements),
and all active monthly summary/envelope queries. This deliberately refetches
the authoritative server projections rather than applying a local balance or
budget delta.

## Verification Strategy

Migration tests cover upgrade from `002_accounts`, the `America/La_Paz`
backfill, atomic protected-Category provisioning, constraints, and repeated
upgrade safety. Service and API tests prove atomic Transaction-plus-movement
creation, exact derived balances, Pending fallback and protection, Plan
isolation, UUID replay/conflict behavior, float and incompatible-currency
rejection, archived-Account posting rejection, and no forbidden endpoints or
fields. Correction tests independently cover amount, Account, Category,
timestamp, merchant, and memo, asserting before/after snapshots, original /
compensation / replacement movement chains, every affected Account balance,
old/new month and Category activity, and immutable history. A synchronized
PostgreSQL test submits two different corrections concurrently for one
Transaction and asserts one compensation per effective movement, ordered
sequences, final balance, canonical projection, monthly/category activity, and
complete history. Budget tests cover local month boundaries (including an IANA
DST boundary), exact assignments, concurrent assignment UUID replay/conflict,
and explicit exclusion/reporting of unconverted currencies. Client tests cover
taxonomy creation/archive and Pendientes protection, posting, correction and
history, authoritative balance/budget refetch, assignment, and unconverted
display.
