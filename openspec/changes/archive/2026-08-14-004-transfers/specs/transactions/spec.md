# Transactions delta

## MODIFIED Requirements

### Requirement: Manual income and expense transaction contract
After `004-transfers`, the persisted Transaction type set MUST include
`transfer`, but the generic public transaction-create operation MUST continue
to create only `income` and `expense`. A `transfer` Transaction MUST be created
only as an immutable leg of the Plan-scoped Transfer API. Income and expense
continue to require an active same-Plan Category; a transfer leg MUST have no
Category. Every transfer leg's Account, currency, amount, timestamp,
provenance, and transfer identity/role MUST be retained as its immutable
canonical leg projection.

At the SQL boundary, every `Transaction(type=transfer)` MUST reference exactly
one same-Plan transfer leg and every leg MUST reference exactly one such
Transaction; income/expense Transactions MUST not be linked as legs. If posted
movements retain `transaction_type`, its value MUST equal the referenced
Transaction type on every row. A `transaction_type=transfer` movement MUST be
the unique original movement of its leg Transaction, never an orphan or a
movement of an income/expense Transaction.

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

#### Scenario: Generic transaction route rejects a transfer
- **GIVEN** a Plan and active Account
- **WHEN** a client submits `type: transfer` to `PUT /plans/{plan_id}/transactions/{transaction_id}`
- **THEN** the request is rejected and no Transaction or movement is written.

### Requirement: Atomic idempotent posting and derived Account effects
The one-Transaction/one-original-movement invariant remains mandatory. A
Transfer is the exception only at the operation level: it atomically creates
two linked transfer Transactions, each with its own exactly one original
movement. Transfer movement signs MUST be determined by leg role, not by an
income/expense classification, and both movements MUST be committed or rolled
back with the Transfer root. The deferred PostgreSQL boundary permits the root,
Transactions, links, and movements to be inserted in one transaction before the
pair is complete, then rejects any missing, duplicate, non-original, cross-Plan,
or type-mismatched final state at commit.

#### Scenario: Retry a manual expense
- **GIVEN** a client UUID and a valid canonical expense payload
- **WHEN** the request is submitted twice and then submitted with the same UUID but a different amount
- **THEN** the first response is `201`, the identical replay is `200` with one Transaction and one movement, and the different replay is `409` without mutation.

#### Scenario: Roll back a failed posting
- **GIVEN** a valid manual income request whose movement write cannot complete
- **WHEN** the posting transaction fails
- **THEN** neither the Transaction nor any Transaction--Tag association, movement, or durable creation identity remains committed.

#### Scenario: Preserve one original movement per transfer leg
- **GIVEN** a successfully posted Transfer
- **WHEN** its two leg Transactions are inspected
- **THEN** each has exactly one immutable original movement and neither has a compensation or replacement movement.

### Requirement: Immutable, compensating Transaction correction
Generic correction applies only to income and expense Transactions. Immediately
after the correction service locks and resolves a Transaction's type—and before
it reads or constructs correction history, snapshots, Tags, or an effective
movement—the service and SQL boundary MUST reject `type=transfer`. This applies
even if a corrupt direct-SQL write has temporarily left that Transaction without
an identifiable leg. Transfer financial history may be changed only by the
Transfer reversal API, which creates a new linked pair and never updates an
existing Transaction, movement, or correction chain.

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

#### Scenario: Reject generic correction of a transfer Transaction early
- **GIVEN** a Transfer leg Transaction or a corrupt/unlinked Transaction whose type is `transfer`
- **WHEN** a client submits `PUT /plans/{plan_id}/transactions/{leg_id}/corrections/{correction_id}`
- **THEN** it receives `409 Conflict` before correction history, snapshots, Tags, or an effective movement are read, no correction or movements are appended, and canonical history remains unchanged.

### Requirement: Concrete Plan-scoped ledger API
The ledger API MUST expose Transfer create/read/reversal routes defined by the
Transfers capability. Transaction read responses for transfer legs MUST expose
their `transfer_id` and `transfer_role`; the Plan Transaction/activity list
MUST return the two legs as one grouped Transfer activity item keyed by the
root UUID. No Transaction PATCH, DELETE, or route that detaches a transfer leg
MAY be exposed.

#### Scenario: Read an Account's posted balance
- **GIVEN** an Account has one posted income of `10.00` and one posted expense of `3.25` in its currency
- **WHEN** its Plan-scoped balance route is queried
- **THEN** it returns the exact derived balance `6.75` in that currency and does not expose an editable accumulator.

#### Scenario: Read grouped Plan activity
- **GIVEN** a Plan contains one expense and one Transfer
- **WHEN** Plan Transaction/activity is read
- **THEN** it contains one ordinary expense item and one Transfer item containing exactly its outbound and inbound legs, not two additional income/expense items.
