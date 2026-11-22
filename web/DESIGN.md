# Numa visual language

## Manual transaction entry

The desktop draft follows the register columns. Headers pair a small icon with
text, share the input alignment, and keep outflows and inflows separate. Save
is the primary action. The phone layout opens an amount-first sheet, with
a reachable add button, local date and readable controls that preserve pinch
zoom. Category and account entry points carry their context into the draft.
Recoverable failures keep the fields editable and retain the transaction ID
for retry. These are the design-huascar checks for the manual entry workflow.

## Monthly budget workspace — 2026-10-21

The user requested YNAB-inspired behavior and hierarchy, explicitly retaining the
Apple Design skill and a usable mobile experience. This iteration follows
`.agents/skills/apple-design/SKILL.md` and preserves the existing visual tokens.

The dedicated Budget destination uses a dark structural account sidebar, a clear
monthly funding status, grouped category rows and an adjacent category inspector.
On narrow phones the rows stack their three monetary values under the category
name; details open in a native bottom sheet. Native modal behavior provides focus
containment, Escape dismissal and an inert background. Labels and financial
states remain textual as well as colored. Immediate press feedback, visible
focus, 44px phone controls, safe-area padding, `dvh`, reduced-motion, reduced-
transparency and increased-contrast handling implement the skill's familiarity,
agency, feedback and flexibility principles. No gesture or spring dependency is
needed for this static, directly activated sheet.

Tests cover exact request strings, Plan scoping, filters, actions, retries, target
editing and month navigation. Real API/PostgreSQL browser checks use synthetic
data, independently of both the user's development records and YNAB account.
See the change verification for current counts, screenshots and boundaries.

The interface follows the supplied editorial finance reference, while keeping
existing routes and financial behavior unchanged. It does not add the reference's
yearly forecast, charts or navigation destinations that Numa has not implemented.

## Tokens

Tokens live in `src/styles.css` and apply to Plans, Accounts, Ledger and Gmail.

| Role | Color |
| --- | --- |
| Paper / page background | `#f3f0e8` |
| Ink / primary text | `#25251f` |
| Muted text | `#696a5e` |
| Fine separators | `#d9d6cd` |
| Terracotta accent | `#b74730` |
| Accent hover / focus | `#963824` / terracotta |
| Sage / active status | `#5d7159` |
| Ochre / unresolved amounts | `#8b601d` |

Serif titles and budget totals, monospaced labels and amounts, a lowercase `numa.`
wordmark, generous whitespace and flat sections replace the previous blue/white
rounded-card theme. The favicon and browser theme color share the same palette.
Fonts use local system stacks, with no remote requests or added dependencies.

## Accessibility and responsive behavior

- Visible keyboard focus, labeled controls, and retained status/error text.
- Controls have a minimum 44px height; labels and long addresses wrap on mobile.
- Single-column forms on small screens; flexible layouts on desktop.
- Color does not replace existing textual status, and reduced-motion preferences
  disable button transitions.
- Text palette meets at least 4.5:1 contrast against the paper background.

## Initial visual pass verification (2026-10-07)

- Frontend suite: 14 passing tests; TypeScript/Vite production build passed.
- Disposable Playwright browser checked all four screens at widths 320, 390 and
  1440px: no horizontal overflow and no browser console errors.
- Desktop and mobile screenshots reviewed. Browser used read-only mocked data,
  with mutation requests blocked; it did not change actual plans, accounts or Gmail.
- Backend, OAuth, ingestion and financial calculations were not edited.

## Interaction and hierarchy pass — apple-design (2026-10-07)

The requested skill is installed **only in this repository** at
`.agents/skills/apple-design/SKILL.md`, a project source discovered by OpenCode.
`skills-lock.json` records the upstream source; the skill includes its MIT license
and source provenance. No global skill/configuration was installed or changed.

### Applied principles

- **Wayfinding / familiarity:** shared plan-scoped Accounts, Ledger and Gmail
  navigation, with `aria-current` and an underlined active destination. On mobile
  this becomes a warm translucent bottom bar; desktop uses a sticky toolbar.
- **Purpose / simplicity:** existing Plans and Accounts precede creation forms.
  Explicit “New plan/account” links lead to the respective forms. Ledger starts
  with the monthly budget and provides native anchor links to Activity, Transfers,
  Reconciliation and Categories instead of one undifferentiated page.
- **Hierarchy:** the large serif budget figure and monospaced assigned/activity
  metrics use existing server-provided strings. No new projections, charts,
  cross-currency sums or client-side financial calculations were introduced.
- **Progressive disclosure:** optional transaction evidence and connection settings
  live in keyboard-operable native `details`. Fields remain mounted and preserve
  their values when closed; request meaning and validation are unchanged.
- **Feedback / responsibility:** immediate press feedback, clear save/loading/error
  states, and simpler amount/date/action labels. Gmail state/counts precede setup;
  mailbox-wide permission and sender-only limitations remain visible before the
  new-connection action. Optional Gmail and immutable financial history remain intact.
- **Flexibility:** layouts support larger text, visible focus, reduced motion,
  reduced transparency and higher contrast. Motion does not block input; no drag,
  spring library or ornamental animation was added without an interaction need.

The user-approved paper/ink/terracotta palette, serif/mono/system font pairing,
wordmark and fine editorial separators are retained. Apple principles improve
behavior rather than replace the reference image's visual identity.

### Checks and boundaries

- Frontend: **19 passing tests**, including active plan navigation, budget-first
  ordering, retained evidence in an exact transaction request and invalid JSON
  blocking submission. Existing correction, transfer/reversal, reconciliation
  snapshot and Gmail action tests still pass; order-dependent test selectors now
  target their semantic regions.
- TypeScript/Vite build and `git diff --check` passed.
- Read-only mocked Playwright review: all four screens at 320, 390 and 1440px,
  no horizontal overflow or browser errors. Also checked all four at 320px with
  200% root text size, keyboard disclosure, same-page draft preservation,
  reduced-motion feedback/focus, and unobscured final actions above mobile navigation.
- Desktop/mobile screenshots reviewed. Real plans, accounts, messages and Google
  authorization were not submitted or changed by browser verification.
- This is not a usability study with real participants. Drafts survive disclosure
  toggles and same-page jumps; cross-route/reload draft persistence is not added.
  Other deferred product capabilities (including Binance parsing) remain deferred.

## Gmail review extension (2026-10-08)

The approved initial Binance Card scope adds a read-only review section before
connection setup. Exact reported USD and merchant are foregrounded; unresolved
settlement and no-posting status stay visible, not buried in a disclaimer.
Unsupported notices show a reason instead of inferred financial amounts.
Source identifiers/parser version remain in native `details`; no source HTML is
rendered. Cursor pagination uses “Load more notices” without losing loaded items.

Ivory/ink/terracotta, serif headings, monospaced amounts and the existing mobile
navigation are retained. Provenance stacks vertically on small screens, including
200% root text size. No financial approval controls or new dependencies were added.
Verified: 23 frontend tests, TypeScript/Vite build, mocked browser review at
320/390/1440px, keyboard disclosure, pagination and no browser errors/overflow.
The earlier “Binance parsing deferred” boundary above describes the previous pass;
settlement, posting and unsampled templates remain deferred in this extension.


## Shared Plan workspace correction — 2026-10-21

Budget, All activity, Accounts and Gmail now use one parent route and one mounted
workspace frame. The same account sidebar, active destinations, header scale,
content width, palette and panel surfaces remain throughout navigation. On phones
all four destinations retain the same compact navigation and wrapping controls.
All activity starts with recorded movements; its duplicate legacy Budget panel
was removed in favor of the dedicated Budget destination.

Apple Design principles applied: spatial consistency across destinations, visible
current location, immediate press feedback, a keyboard skip link, focus to page
content on navigation, 44px touch controls and reduced-transparency/contrast
fallbacks. Existing forms, corrections, transfers, reconciliation and Gmail
operations remain available.

Verification: 33 frontend tests and production build passed, including a test that
checks the exact same sidebar DOM node across all routes and one that navigates
away from failed Budget content. Read-only synthetic Playwright inspection passed
at 320/390/1440px and 320px with 200% text on every destination, with no horizontal
overflow or console errors. Screenshot artifacts use invented data.

## YNAB-inspired usability pass — 2026-10-28

The editorial identity remains: paper, ink, terracotta, serif screen titles, monospaced amounts and flat separators. The change is structural rather than a palette swap.

- The workspace brand strip and page headers are shorter, budget rows are denser, and the permanent month panel is more compact. At 1280×720 the first category now starts around `y=343` instead of `y=455`.
- Exact money strings are formatted for display without converting to `Number`: `Bs 2.625,94`, `-Bs 1.961,90`, `1,000000 USDT`. Requests and audit snapshots keep the authoritative server strings.
- Goal rows show a compact status badge, a small completion mark and a thin server-calculated progress line. Progress is returned by the budget projection; the client never computes a financial ratio.
- Transactions are now a dense register table with date, account, payee, category, memo, outflow/inflow and an inline correction row. Search, account and type filters are available without leaving the register.
- Corrections expose account, category, date, merchant, memo and tags while preserving the original entry and correction history.
- Account cards link directly to their filtered register; the activity header shows the account context, and the sidebar exposes archived accounts under `Closed accounts`.
- The add form is compact and follows the register, so the daily transaction view is visible first. Advanced evidence stays in a native disclosure.

Verification: frontend tests, TypeScript/Vite build, full backend suite against a clean PostgreSQL database, and headless Playwright review at desktop and 390px. No development or YNAB records were changed by the browser review; populated screenshots used intercepted synthetic responses.
