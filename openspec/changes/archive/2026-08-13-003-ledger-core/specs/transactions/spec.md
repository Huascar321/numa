# Transactions delta

## ADDED Requirements

### Requirement: Ledger-core migration and Plan-local taxonomy persistence
Alembic revision `003_ledger_core` MUST follow `002_accounts`. It MUST add
Plan-local Category Groups, Categories, Tags, Transaction--Tag associations,
Transactions, posted Account movements, and immutable Transaction correction
history. Monetary values in these tables MUST use PostgreSQL `NUMERIC` or
integer atomic units and MUST NOT use `REAL`, `DOUBLE PRECISION`, or a
floating-point representation.

Each Category Group, Category, and Tag MUST belong to exactly one Plan. A
Category MUST persist its direct Plan owner and MAY refer to a Category Group;
when it does, the Group MUST belong to that same Plan. Transactions,
movements, Tags, Transaction--Tag associations, and correction snapshots MUST
also preserve Plan ownership. Database constraints and Plan-scoped queries MUST
reject every cross-Plan reference.

Category Group, Category, and Tag PUT creation MUST use the client UUID as a
transactional idempotency identity. Concurrent identical requests MUST produce
one durable resource and one `201` plus one `200`; concurrent different payloads
with the same UUID MUST produce one `201` plus one `409`, never `500` or a
partial taxonomy resource.

#### Scenario: Reject a cross-Plan category reference
- **GIVEN** a Category belongs to Plan A and an Account belongs to Plan B
- **WHEN** a Transaction for Plan B names the Category from Plan A
- **THEN** the request is rejected, no Transaction or movement is written, and no data from Plan A is disclosed.

### Requirement: Protected Pendientes Category and non-destructive taxonomy lifecycle
Every Plan MUST always have exactly one active protected Category named
`Pendientes`. The `003_ledger_core` migration MUST create it for every existing
Plan. Creation of every new Plan MUST atomically create its `Pendientes`
Category. The protected Category MUST NOT be renamed, moved, archived,
deleted, or replaced.

Category Groups, ordinary Categories, and Tags MUST use non-destructive,
one-way archive lifecycle operations. An ordinary Category with Transaction,
movement, correction, or assignment history MUST be archived without physical
destruction and remain readable through its historical references. New
postings and assignments MUST NOT select an archived Category or Tag. A
Category Group with active Categories MUST NOT archive until those Categories
are archived or moved within the same Plan. This change MUST expose no DELETE
endpoint for these resources.

#### Scenario: Migrate an existing Plan
- **GIVEN** a database at `002_accounts` with an existing Plan
- **WHEN** `003_ledger_core` is applied
- **THEN** that Plan has one active protected Category named `Pendientes` and no other Plan's taxonomy is changed.

#### Scenario: Attempt to change Pendientes
- **GIVEN** a Plan has its protected `Pendientes` Category
- **WHEN** a client attempts to rename, archive, move, or delete it
- **THEN** no mutation occurs and the protected Category remains active with its exact name.

### Requirement: Manual income and expense transaction contract
The public ledger operation in this phase MUST create only `income` and
`expense` Transactions. Every Transaction MUST persist a client-generated UUID
and immutable creation fingerprint; Plan and Account; type; positive exact
amount and currency; an offset-aware timestamp; Category; merchant; memo;
optional opaque photo reference; Tags; optional Location; source; source
metadata; provenance; and creation/update timestamps. The public source for
this operation MUST be `manual`; original source metadata and provenance MUST
remain reviewable after correction. Photo references MUST NOT imply a binary
storage, upload, or retrieval implementation.

The amount MUST be supplied as a decimal string, parse exactly without rounding,
be positive, and be representable at the Account currency's declared scale.
JSON numeric money values, including floats, MUST be rejected. The supplied
currency MUST equal the Account currency. The Account and Category MUST belong
to the Plan, and the Account MUST be active. If Category is omitted, the
Transaction MUST use that Plan's protected `Pendientes` Category. Tags MUST be
active and belong to that same Plan.

`reconciliation_adjustment` is reserved for `006-reconciliation` and MUST have
no public creation endpoint in this change. `transfer` MUST NOT be implemented
until `004-transfers`. Transactions MUST NOT have a `cleared` field.

#### Scenario: Create an uncategorized expense
- **GIVEN** an active BOB Account in a Plan
- **WHEN** a client creates an exact BOB expense without a Category
- **THEN** the Transaction uses that Plan's `Pendientes` Category and records all required manual provenance fields.

#### Scenario: Reject imprecise or incompatible money
- **GIVEN** an active BOB Account
- **WHEN** a client submits a JSON float, a non-representable decimal, or a USDT currency for an income or expense
- **THEN** the request is rejected and no Transaction, movement, or idempotency record is created.

#### Scenario: Reject a posting to an archived Account
- **GIVEN** an archived Account with readable historical movements
- **WHEN** a client creates an income or expense for it
- **THEN** the request is rejected and its historical balance remains unchanged.

### Requirement: Atomic idempotent posting and derived Account effects
A successful Transaction creation MUST write the canonical Transaction, its
current Transaction--Tag associations, and exactly one posted Account movement
in one PostgreSQL transaction. Income MUST create a positive signed movement;
expense MUST create a negative signed movement. A failed create MUST leave none
of those records durable.

The client UUID is the Transaction idempotency identity. The first canonical
request MUST return `201 Created`; an identical replay MUST return `200 OK`
with the existing current Transaction; reuse of the UUID with a different
canonical creation payload MUST return `409 Conflict` and MUST NOT alter the
original Transaction or movements. A posted movement MUST retain the Account,
currency, signed amount, transaction type, effective timestamp, Category, and
audit snapshot needed to derive balances and budget activity.

The UUID semantics MUST remain concurrency-safe: concurrent identical requests
MUST result in exactly one durable Transaction, one original movement, and one
set of current Tag links, with one `201` and one `200`. Concurrent requests with
different canonical payloads but the same UUID MUST result in one `201` and one
`409`, never a `500`, and MUST leave no partial effect from the conflict.

#### Scenario: Retry a manual expense
- **GIVEN** a client UUID and a valid canonical expense payload
- **WHEN** the request is submitted twice and then submitted with the same UUID but a different amount
- **THEN** the first response is `201`, the identical replay is `200` with one Transaction and one movement, and the different replay is `409` without mutation.

#### Scenario: Roll back a failed posting
- **GIVEN** a valid manual income request whose movement write cannot complete
- **WHEN** the posting transaction fails
- **THEN** neither the Transaction nor any Transaction--Tag association, movement, or durable creation identity remains committed.

### Requirement: Immutable, compensating Transaction correction
The API MUST correct a Transaction by creating an immutable, client-UUID
identified correction event. Each correction MUST preserve the previous and
replacement snapshots, correction provenance, and timestamps. It MUST NOT
delete or update a historical posted movement in place.

In one PostgreSQL transaction, correction MUST append a compensating movement
for the currently effective prior movement and a replacement movement for the
corrected snapshot, then update the canonical current Transaction projection.
The compensating movement MUST have the inverse signed amount and the prior
Account, Category, timestamp, merchant, and memo snapshot; the replacement
must use corrected facts. The compensating movement's effective timestamp MUST
be the prior timestamp and the replacement movement's effective timestamp MUST
be the corrected timestamp. Tag changes MUST retain prior Transaction--Tag link
history. Correction replays MUST use `201` / `200` / `409` behavior equivalent
to Transaction creation.

Before reading any correction snapshot, Tag state, or effective movement, the
server MUST lock the Plan-scoped Transaction with `SELECT ... FOR UPDATE`.
Each correction MUST receive a monotonic `correction_sequence` that is unique
for that Transaction. The original movement is sequence zero and the effective
movement is the replacement linked to the greatest committed correction
sequence. The sequence, rather than `created_at`, `posted_at`, or UUID order,
MUST determine the correction chain. The compensation MUST be the exact inverse
of the effective movement read after that lock. Concurrent corrections for one
Transaction MUST serialize and have the same result as their lock-order
sequential execution.

Correction UUID creation MUST use the same transactional conflict-safe
algorithm as Transaction creation. Concurrent identical correction requests
MUST return one `201` and one `200` with one durable correction and one pair of
movements. Different payloads with one correction UUID MUST return one `201`
and one `409` with no partial second pair.

#### Scenario: Correct financial and descriptive facts
- **GIVEN** a posted expense
- **WHEN** independent corrections change amount, Account, Category, timestamp, merchant, and memo
- **THEN** prior movements and correction snapshots remain immutable, Account balances equal the sum of all posted movements, old and new Category/month activity net correctly, and merchant/memo corrections preserve unchanged net financial effects.

#### Scenario: Serialize different concurrent corrections
- **GIVEN** one posted Transaction and two different valid corrections submitted at the same time
- **WHEN** PostgreSQL commits both correction requests
- **THEN** the corrections have consecutive unique sequences, each compensation inverses exactly the movement effective immediately before that sequence, no movement is compensated twice, the final Account balances equal the complete movement sum, the canonical Transaction equals the last after-snapshot, monthly and Category projections are coherent, and both immutable history records are retained.

#### Scenario: Preserve each correction field's audit chain
- **GIVEN** a posted expense
- **WHEN** separate corrections independently change amount, Account, Category, timestamp, merchant, and memo
- **THEN** every correction contains the exact before/after snapshots, every correction appends one original-effective compensation and one replacement, all involved Account balances and old/new month/category activity are correct, merchant/memo changes have net-zero financial effect, and prior movements and corrections cannot be updated or deleted.

### Requirement: Concrete Plan-scoped ledger API
The server MUST expose the following Plan-scoped routes:

- `PUT /plans/{plan_id}/category-groups/{group_id}`, `GET /plans/{plan_id}/category-groups`, `GET /plans/{plan_id}/category-groups/{group_id}`, `PATCH /plans/{plan_id}/category-groups/{group_id}`, and `POST /plans/{plan_id}/category-groups/{group_id}/archive`;
- `PUT /plans/{plan_id}/categories/{category_id}`, `GET /plans/{plan_id}/categories`, `GET /plans/{plan_id}/categories/{category_id}`, `PATCH /plans/{plan_id}/categories/{category_id}`, and `POST /plans/{plan_id}/categories/{category_id}/archive`;
- `PUT /plans/{plan_id}/tags/{tag_id}`, `GET /plans/{plan_id}/tags`, `GET /plans/{plan_id}/tags/{tag_id}`, `PATCH /plans/{plan_id}/tags/{tag_id}`, and `POST /plans/{plan_id}/tags/{tag_id}/archive`;
- `PUT /plans/{plan_id}/transactions/{transaction_id}`, `GET /plans/{plan_id}/transactions`, `GET /plans/{plan_id}/transactions/{transaction_id}`, `GET /plans/{plan_id}/transactions/{transaction_id}/corrections`, and `PUT /plans/{plan_id}/transactions/{transaction_id}/corrections/{correction_id}`; and
- `GET /plans/{plan_id}/accounts/{account_id}/balance`.

PUT paths MUST use client-generated UUIDs and idempotent `201` / `200` / `409`
semantics. PATCH MUST only change allowed ordinary taxonomy fields; archive is
the only lifecycle mutation. The account balance response MUST contain the
exact decimal-string balance in that Account's currency. No DELETE route,
transfer-create route, reconciliation-adjustment-create route, `cleared` route,
or binary-photo route MAY be exposed.

#### Scenario: Read an Account's posted balance
- **GIVEN** an Account has one posted income of `10.00` and one posted expense of `3.25` in its currency
- **WHEN** its Plan-scoped balance route is queried
- **THEN** it returns the exact derived balance `6.75` in that currency and does not expose an editable accumulator.

### Requirement: Minimal authoritative ledger UI
The React client MUST provide Plan-scoped flows for Category Groups, Categories,
and Tags; a manual income/expense form; Transaction listing, detail, and
correction; and a basic monthly budget view. It MUST submit client UUIDs and
exact decimal-string money, render server-authoritative balances and history,
and clearly show the protected `Pendientes` state. It MUST not offer DELETE,
transfer, reconciliation, `cleared`, photo binary upload, final navigation, or
advanced visual design in this phase.

#### Scenario: Correct a Transaction in the client
- **GIVEN** a listed manual Transaction
- **WHEN** a user opens its detail, changes an allowed fact, and submits a correction UUID
- **THEN** the UI refreshes the authoritative current Transaction and displays its retained correction history without offering destructive deletion.
