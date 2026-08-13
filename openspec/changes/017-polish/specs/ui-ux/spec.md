# UI/UX delta

## ADDED Requirements

### Requirement: Exact responsive PWA navigation
Primary navigation MUST be Home/Transactions/Plan/Analytics/More, with the specified Accounts, Goals, Statements, Pending, Watchers, Automation Suggestions, Categories, Tags, and Settings items under More.

#### Scenario: Stale offline read
- **WHEN** the network is unavailable
- **THEN** cached finance data is labeled stale and unsupported writes are not presented as committed.
