# Transfers delta

## ADDED Requirements

### Requirement: Atomic linked transfer
Transfers MUST post paired linked legs atomically; same-currency absolute amounts MUST match and transfers MUST have no category.

#### Scenario: Cross-currency transfer
- **WHEN** BOB is exchanged for USDT
- **THEN** sent and received originals, currencies, rate, source, and timestamp remain stored.

### Requirement: Transfer reporting exclusion
Transfer legs MUST be excluded from income, expense, Ready to Assign, and category activity.

#### Scenario: Transfer reporting
- **WHEN** a linked transfer posts
- **THEN** it changes account balances but not income or expense totals.
