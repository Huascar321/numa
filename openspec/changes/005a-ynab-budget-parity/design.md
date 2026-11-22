# Design

## Context

See proposal.md. Baseline tests: 295 backend and 23 frontend passing. The user
authorized implementation, including a scoped exception to prior simplified
card behavior and phase order. Prior changes and unrelated local work stay intact.
Read-only YNAB exploration on 2026-10-21 confirmed grouped monthly rows, left
account navigation, a category inspector, target forms and move-money popovers.
No financial changes or saves were submitted in that account.

## Goals / Non-Goals

Implement a coherent envelope workflow, rather than general feature parity with
all of YNAB. Keep the current exact ledger, correction history and foreign currency
boundaries. Gmail, imports, AI, offline sync and remote publishing are independent.
Reconciliation adjustments retain their existing exclusion from budget activity;
they are shown separately so no undisclosed change to reconciliation policy occurs.

## Decisions

- Build a single server projection from bounded Plan-scoped queries, replaying
  months from earliest relevant fact. Preserve negative Available in the current
  month; carry positive spending-category amounts only, debit past cash deficits
  once, carry unassigned money and deduct net positive future assignments. Use
  Decimal with a precision exceeding NUMERIC(38,18), never floats.
- Keep append-only posted movements as monetary truth. Use current canonical
  transactions for expense allocation after corrections; net movement totals
  retain cross-month compensation. Fund cash before credit within a category.
- Add nullable card-payment account identity to categories, enforce ownership and
  immutability in SQL, and backfill one deterministic category per same-currency
  card. New card creation creates its category atomically. Derive reserves from
  funded spending, direct assignments and transfer legs; show unfunded debt.
  Positive card balances fund cash spending until exhausted; overpayment-created
  credit and same-currency cash advances expose new spendable cash. Debt-reducing
  income does not create cash. These rules were checked against official YNAB
  positive-balance, statement-credit and cash-advance guides on 2026-10-21.
- Add immutable budget action receipts. Serialize actions and legacy assignments
  on their Plan, resolve UUID retries before recalculating, and write compensating
  assignment pairs in one transaction. Insufficient-source moves fail atomically.
- Extract BudgetScreen/BudgetPanel into a dedicated React module. Reuse React
  Query, refetch all affected budget months, preserve the existing visual palette
  while adopting YNAB's hierarchy and dense grouped rows. Client code formats and
  classifies strings but never computes financial balances.

## Risks / Trade-offs

- Historical projection changes are observable: regression tests use multi-month
  examples, debt, payments, mixed spending, corrections and Plan isolation.
- Payment categories add taxonomy records but never rewrite ledger evidence.
- Foreign currencies remain visibly unconverted, not a consolidated cash total.
- Reconciliation remains an explicit adjustment outside budget income/activity;
  display that boundary instead of claiming full cash reconciliation equivalence.
- Richer YNAB recurrence options are not implied by the three existing target types.

## Migration Plan

Add revision 010_ynab_budget after 009_watcher_runs. Test clean and populated
upgrades in disposable PostgreSQL before local rollout. Do not downgrade a database
containing new action receipts; reverting code requires restoring a compatible
schema version. No production deployment is part of this work.


## Apple design and mobile acceptance

The user explicitly required `.agents/skills/apple-design/SKILL.md`. Keep the
existing paper/ink/terracotta identity, use immediate press feedback and visible
focus, and make small-screen category details a native modal sheet. The browser
manages focus containment, Escape and inert background. Use `dvh`, safe areas,
44px touch targets, readable stacked mobile rows, reduced motion/transparency
and high-contrast fallbacks. Test 320/390px, 200% text, keyboard and error/success
feedback inside the sheet; desktop uses an adjacent inspector.

## Shared workspace correction — 2026-10-21

The user reported that leaving Budget returned abruptly to the previous layout.
Extract the frame into a parent nested route around all four Plan destinations.
Keep account data in shared React Query keys and preserve the sidebar DOM across
navigation. Use the original Budget surfaces and compact typography for Accounts,
activity and Gmail; activity starts with movements, with budget funding kept on
its dedicated destination. Shared focus/scroll handling and a skip link support
keyboard wayfinding. Preserve all existing financial and Gmail operations.
