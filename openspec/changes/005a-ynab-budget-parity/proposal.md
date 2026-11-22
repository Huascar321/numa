# Proposal

## Why

The monthly Ready to Assign calculation loses unassigned money between months,
and the minimal budget screen hides overspending and target controls. The user
explicitly requested functional and visual adaptation toward YNAB on 2026-10-21.

## What Changes

- Preserve unassigned money and overassignment across months, with explicit
  future funding and no inclusion of future income.
- Show signed category availability, cash versus credit overspending, targets,
  and funding actions in a grouped monthly budget workspace.
- Activate credit-card payment reserves and auditable movement of budget money.
- Keep exact server-side money, original ledger history, independent Plans,
  explicit foreign currencies and existing Gmail/reconciliation functionality.
- Use YNAB's public guidance and the user's read-only reference session to check
  behavior and hierarchy. Never copy account data into fixtures or assets.

This is an explicitly authorized follow-up to 005, ahead of unrelated pending
phases. It supersedes the simplified-card/no-payment-reserve restrictions only
within this scoped change. Earlier change artifacts remain historical evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `budgeting`: continuous funding, visible overspending, payment reserves,
  atomic budget moves and usable target controls.
- `ui-ux`: dedicated responsive monthly budget with grouped rows, clear money
  states, category details and persistent account navigation.

## Impact

Budget projections, additive schema for card payment categories, account creation,
budget API/contracts, React budget/navigation/styles, targeted regression tests
and documentation. Existing financial records are not rewritten. No remote
publication, Gmail scope change or external-account mutation is included.
