# Verification — 2026-10-21

## Scope and reference

The user requested implementation, functional and visual adaptation toward YNAB,
and explicitly required the local Apple Design skill with a usable mobile layout.
The scoped follow-up supersedes the earlier simplified card policy without
implementing unrelated roadmap phases or changing historical change artifacts.

Read-only exploration used the user-authorized persistent browser profile. Inspected
the grouped monthly grid, category inspector, unsaved target form, move-money
dialog and card inspector. Closed/cancelled forms without financial saves. No
reference-account balances, addresses, category names or screenshots were copied
into source, fixtures, documentation or repository screenshots. Repository browser
artifacts use invented data in a disposable local database.

Public behavior references checked on 2026-10-21:

- [Monthly rollover](https://support.ynab.com/en_us/when-the-month-rolls-over-a-guide-rkyyd6qC9)
- [Card payments](https://support.ynab.com/en_us/credit-card-payments-a-guide-r1_506Q1j)
- [Positive card balances](https://support.ynab.com/en_us/credit-cards-with-a-positive-balance-an-overview-By_H6uzJo)
- [Statement credits](https://support.ynab.com/en_us/how-to-handle-credit-card-rewards-and-statement-credits-a-guide-ryoRzYY0q)
- [Cash advances](https://support.ynab.com/en_us/credit-card-cash-advances-an-overview-Hy6PmlOC9)

## Implementation evidence

- Continuous Ready to Assign, reserved future assignments without future income,
  signed availability, cash-first mixed financing and one-time prior cash deficits.
- Protected budget-currency card payment categories with additive backfill, funded
  purchase reserves, direct old-debt funding, actual payment/reversal effects and
  explicit unfunded debt. Positive card credit is spendable cash; only debt-creating
  spending is reserved. Debt-reducing credits do not invent income.
- Immutable action receipts and signed assignment adjustments, Plan serialization,
  action UUID serialization, canonical exact-money retries, conflicting reuse,
  insufficient-source rejection and no account movements from budget actions.
- Target shortfalls represent additional money needed; target controls save,
  remove and fund through explicit server actions. Form values refresh after funding.
- Dedicated workspace at `/plans/{plan_id}/budget`, account navigation to filtered
  ledger activity, grouped rows, money-state filters and category details.

## Automated validation

Baseline before implementation: **295 backend / 23 frontend**, full build passing.
Final full run: **310 backend passed, 0 skipped; 31 frontend passed; TypeScript/Vite
build passed**. Existing non-failing Starlette/httpx and Pydantic warnings remain.
Strict validation of this change and `git diff --check` passed.

Backend checks use randomly created PostgreSQL 18 databases at test port 29746,
never the development database. Migration tests check both clean and populated
upgrades, repeated application, protected SQL identities and unchanged old rows.
Existing Gmail, Binance, watchers, transfers and reconciliation remain covered.

## Browser validation

Real synthetic API at 39749 with a disposable database; Vite at 5174.
Both temporary servers were stopped and the synthetic database removed.
Temporary reference-account artifacts were removed; its persistent browser
profile and open YNAB session remain intact.
Verified grouping and filters, covering a 50.00 deficit via a money move, target
edit/funding, refreshed input amounts, mobile sheet focus containment after 20 Tab presses, Escape, reduced motion,
increased contrast, and visible
insufficient-source errors inside the modal. The intentionally invalid move
returned HTTP 422; that expected failed resource is the only browser console
error observed. No unhandled application error was observed.

Checked 320, 390, 768 and 1440px: no horizontal page overflow. A 320px/200% root
text check initially exposed navigation/month-header overflow; fixed it and
verified no overflow. The modal itself also has no horizontal overflow. Native
phone keyboard and physical iOS Safari remain human-device validation boundaries.

Synthetic screenshot artifacts are under ignored `output/playwright/`, including
`budget-desktop.png`, `budget-mobile.png` and `budget-mobile-sheet.png`.

## Local rollout and preservation

Applied `009_watcher_runs → 010_ynab_budget` only on isolated development PostgreSQL
at 39747. Compared all original columns and rows in **20 existing tables / 511
records** before/after: **unchanged**. Existing categories retain original facts;
new payment categories are additive. This development database had no eligible
credit cards, so zero payment categories were backfilled. No ledger posting,
budget action, Gmail collection or Google reauthorization was performed against
development data during rollout. No worker was started.

API 39748 and web 5173 serve the updated local workspace; both direct and proxied
readiness checks return HTTP 200. No commit, push, archive or remote deployment.

## Explicit boundaries

This is the core envelope workflow, not full YNAB feature parity. Different
currencies are never silently combined. Reconciliation retains its existing
outside-budget funding policy and exposes adjustments separately. Existing three
target types do not imply every YNAB recurrence, scheduled transaction, reporting,
refund workflow, import or offline feature. Existing uncommitted work is preserved.


## Shared workspace follow-up — 2026-10-21

The user reported an abrupt visual change outside Budget. Extracted a persistent
parent Plan route and shared frame for Budget, All activity, Accounts and Gmail.
Sidebar identity, account data, selected navigation, compact headers and surfaces
now remain consistent. Removed the duplicate legacy budget from All activity and
kept funding on its dedicated route. Keyboard navigation gains a skip link and
content focus; existing controls retain their operations.

- **33 frontend tests passed** and TypeScript/Vite build passed. Existing posting,
  correction, transfer/reversal, reconciliation, taxonomy, account and Gmail tests
  remain green. Navigation regression checks the same sidebar DOM across all four
  routes, including escape from a failed Budget load.
- Read-only synthetic browser routes blocked mutations. All four destinations
  passed 320, 390 and 1440px and 320px/200% text without horizontal overflow.
  The section links on activity initially overflowed; explicit wrapping fixed it.
- Browser confirmed the same sidebar DOM after every navigation; console showed
  zero errors/warnings. Desktop/mobile screenshots are `shared-*-desktop.png` and
  `shared-*-mobile.png` under ignored `output/playwright/`.
- This follow-up changed frontend and documentation only. No backend code,
  development records, credentials, Google authorization, migrations or publishing.
