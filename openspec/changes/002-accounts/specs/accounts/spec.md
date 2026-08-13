# Accounts delta

## ADDED Requirements

### Requirement: Plan-scoped account registry
Plans MUST own Bank, Cash, Wallet, Credit Card, Crypto, and Other accounts with an explicit ISO/custom currency.

#### Scenario: Create account
- **WHEN** a user creates an account in a plan
- **THEN** type, currency, and lifecycle are stored in that plan.

### Requirement: Derived account balance
Balances MUST derive from posted ledger movements and confirmed reconciliation adjustments.

#### Scenario: Close historical account
- **WHEN** an account with history is archived
- **THEN** history remains readable and new postings are blocked.
