# Monthly budget workspace delta

## ADDED Requirements

### Requirement: Usable monthly budget workspace
The UI MUST expose a dedicated budget destination with previous/next month controls,
Ready to Assign status, account navigation, category groups and Assigned/Activity/
Available columns. Selecting a category MUST expose funding, move-money and target
controls plus rollover and overspending details. Filters MUST expose underfunded,
overspent and available categories. Payment reserves MUST be clearly distinct
from spending. The workspace MUST use server-authoritative decimal strings,
accessible labels, keyboard focus and responsive layouts without horizontal page
overflow at 320px. Existing Accounts, Ledger and Gmail MUST remain reachable.

#### Scenario: Cover overspending
- **GIVEN** a category has negative Available
- **WHEN** the user selects the overspent filter and category
- **THEN** the signed deficit and money-moving controls MUST be accessible with
  explicit source and destination, followed by refetched server balances.

### Requirement: Persistent Plan workspace across destinations
Budget, All activity, Accounts and Gmail MUST share one persistent Plan workspace,
with the same sidebar, account balances, selected navigation, typography and
responsive structure. Changing destinations MUST preserve the workspace frame.
All activity MUST open recorded movements and MUST NOT duplicate the old budget
screen. Loading and error content MUST remain inside the shared frame. Navigation
MUST retain keyboard access, clear focus and phone layouts with 200% text support.

#### Scenario: Navigate away from Budget
- **GIVEN** the monthly Budget is visible
- **WHEN** the user opens All activity, Accounts or Gmail and returns
- **THEN** the same sidebar MUST remain mounted, the active destination MUST update,
  and page contents MUST use consistent headers, spacing and surfaces.
