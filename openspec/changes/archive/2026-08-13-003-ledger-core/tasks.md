# Tasks

## 1. PostgreSQL migration and persistence

- [x] 1.1 Add Alembic revision `003_ledger_core` after `002_accounts`; add non-null immutable `plans.budget_timezone`, backfill every existing Plan explicitly to `America/La_Paz`, and require a valid IANA timezone for new Plans.
- [x] 1.2 Create Plan-scoped `category_groups`, `categories`, and `tags` with UUID identities, exact lifecycle constraints, timestamps, idempotency fingerprints, same-Plan references, and archive-only behavior; model the protected `Pendientes` Category and enforce its exact name, uniqueness, and immutable active state.
- [x] 1.3 Backfill exactly one protected `Pendientes` Category for each existing Plan and make new-Plan insertion plus protected-Category provision atomic; test rollback leaves no partial Plan or taxonomy resource.
- [x] 1.4 Create `transactions`, append-only Transaction--Tag association history, `posted_account_movements`, and immutable `transaction_corrections` with UUIDs, Plan-scoped composite foreign keys, `TIMESTAMPTZ` event/posting times, source metadata/provenance, opaque photo references, optional locations, and no `cleared` or editable balance columns.
- [x] 1.5 Create `monthly_budget_assignments` with Plan/Category/month identity, exact signed `NUMERIC` amount, budget-currency validation, immutable provenance and creation fingerprints; prohibit floating-point money columns throughout the revision.
- [x] 1.6 Add PostgreSQL migration tests from an empty database and a database at `002_accounts`, including repeated `upgrade head`, timezone/Pendientes backfill, constraints/indexes/composite Plan isolation, absence of forbidden fields, and readiness at `003_ledger_core`.

## 2. Domain models and ledger services

- [x] 2.1 Define typed exact-money, timezone-aware timestamp, IANA timezone, Category Group, Category, Tag, Transaction, movement, correction, Transaction--Tag, assignment, monthly summary, envelope, and unconverted-currency contracts; accept decimal strings or exact atoms only and reject floats without rounding.
- [x] 2.2 Implement Plan creation extension that validates and persists the immutable IANA budget timezone and atomically provisions the protected `Pendientes` Category for client-UUID-idempotent Plan creation.
- [x] 2.3 Implement Plan-scoped Category Group, Category, and Tag create/read/update/archive services with client UUID idempotency, same-Plan relation validation, protected Pendientes mutation guards, historical readability, and no destructive delete service.
- [x] 2.4 Implement manual Transaction creation for `income|expense` only: validate active Account, exact positive currency-compatible amount, offset-aware timestamp, Category/Tag ownership, default Pendientes, manual source metadata/provenance, optional photo reference/location, and `201`/`200`/`409` UUID semantics, including concurrent UUID replays and conflicts.
- [x] 2.5 Implement a single PostgreSQL posting transaction that creates the canonical Transaction, current Tag links, and one signed posted movement; verify income is positive, expense is negative, and any failure rolls back every write, including concurrent requests.
- [x] 2.6 Implement the Account balance projection exclusively as the exact sum of posted movements and reuse it in Account reads and the dedicated balance service; retain readable balances for archived Accounts while blocking new postings.
- [x] 2.7 Implement append-only Transaction correction with idempotent correction UUIDs, immutable before/after/provenance history, compensating old snapshot movement, replacement corrected snapshot movement, and current projection update in one database transaction; lock the Transaction first and assign an ordered correction identity.
- [x] 2.8 Cover amount, Account, Category, timestamp, merchant, and memo corrections; verify compensating/replacement movement chains, exact Account balances, old/new monthly Category activity, immutable historical snapshots for each case, and synchronized concurrent corrections.
- [x] 2.9 Implement immutable idempotent monthly assignment creation and local-month summary/envelope projections using the Plan IANA timezone, exact posted budget-currency movements, and explicit unconverted-by-currency reporting, including concurrent UUID requests.

## 3. FastAPI endpoints

- [x] 3.1 Add the Plan-scoped Category Group, Category, and Tag PUT/GET/PATCH/archive routes specified in the delta; enforce UUID replay/conflict responses, archive rules, Plan isolation, and absence of DELETE routes.
- [x] 3.2 Add `PUT /plans/{plan_id}/transactions/{transaction_id}`, Transaction list/detail/correction-history reads, and idempotent `PUT /plans/{plan_id}/transactions/{transaction_id}/corrections/{correction_id}`; expose only manual income/expense creation.
- [x] 3.3 Add `GET /plans/{plan_id}/accounts/{account_id}/balance` and return the same exact derived balance in Account reads without accepting balance mutation fields.
- [x] 3.4 Add idempotent monthly assignment creation and the Plan-scoped month summary and Category envelope routes, including exact unconverted-by-currency response structures.
- [x] 3.5 Add API integration tests for atomic posting, balance derivation, Pending fallback/protection, Plan isolation, UUID `201`/`200`/`409` under concurrency, float and incompatible-currency rejection, archived Account posting rejection, correction history/effects, IANA month boundaries, assignments, and unconverted reporting.
- [x] 3.6 Confirm API routing and schemas contain no DELETE, transfer creation, `cleared`, reconciliation-adjustment creation, rollover, overspending-policy, Goal, Target, Credit Card automation, currency-conversion, or binary-photo endpoints.

## 4. Minimal React client

- [x] 4.1 Implement Plan-scoped Category Group, Category, and Tag list/create/edit/archive flows using client UUIDs and authoritative query data; clearly identify and disable mutations for Pendientes.
- [x] 4.2 Implement a manual income/expense form with exact decimal-string money, account-currency validation feedback, timezone-aware timestamp, optional Category default, merchant, memo, photo reference, Tags, optional location, and source metadata fields; exclude transfer, cleared, and reconciliation controls.
- [x] 4.3 Implement Transaction list, detail, retained correction history, and correction submission flows; refresh authoritative Transactions, Account balances, monthly summaries, and affected envelopes after posting or correction without destructive controls.
- [x] 4.4 Implement a basic Plan-month budget screen with assignment creation, Ready to Assign, Category Assigned/Activity/Available envelopes, and clearly labeled unconverted amounts by currency; omit rollover, Goals/Targets, Credit Card automation, final navigation, and advanced design.
- [x] 4.5 Add focused client tests for taxonomy creation/archive and Pendientes protection, manual posting, Transaction correction/history, authoritative Account/balance and budget updates, assignment, baseline month display, and explicit unconverted labels.

## 5. Verification and scope guard

- [x] 5.1 Run the PostgreSQL 18 migration, model, service, API, and synchronized concurrency suites from the required database starting points; verify atomic Transaction-plus-movement writes, derived balances, exact-money rejection, UUID idempotency, Plan isolation, archived Account guard, serialized immutable correction chains, and zero omitted PostgreSQL tests.
- [x] 5.2 Run budget calculations across local month boundaries, including an IANA DST boundary, and verify baseline formulas, signed assignments, corrected activity, concurrent assignment idempotency, and exclusion/reporting of every unconverted currency.
- [x] 5.3 Run client tests and production build, then run `openspec doctor`, `openspec validate 003-ledger-core --strict --no-interactive`, `openspec validate --all --strict --no-interactive`, and `git diff --check`; mark task boxes only after their corresponding implementation and verification complete.
- [x] 5.4 Confirm the implementation contains no transfer, `cleared`, reconciliation API, rollover, cross-month overspending policy, Goals, Targets, special Credit Card budget automation, silent currency conversion, binary photo storage, destructive deletion, final navigation, or advanced visual design.
