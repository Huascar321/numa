# Exchange rates delta

## ADDED Requirements

### Requirement: Contextual explicit quote
Quotes MUST preserve side, formula, context, source, and observation time; missing or stale quotes MUST remain visible.

#### Scenario: Manual BUY_USDT quote
- **WHEN** BOB is paid and USDT received
- **THEN** BUY_USDT uses the exact formula and no 6.96 principal is assumed.
