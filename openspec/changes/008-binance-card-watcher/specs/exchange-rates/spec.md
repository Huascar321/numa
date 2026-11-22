# Exchange rates delta

## ADDED Requirements

### Requirement: No implicit reported-currency conversion
Reported card currency MUST remain distinct from any settlement quote until
authoritative account mapping or settlement evidence plus explicit deterministic
configuration or review resolves it. A generic rule alone MUST NOT equate
reported USD to USDT.
This initial scope MUST NOT resolve settlement, create FX quotes, or post
transactions even if an account happens to use USDT. Only observed USD successes
are extracted; other reported currencies require review without inferred amounts.

#### Scenario: USD notice
- **WHEN** a notice reports USD without settlement evidence
- **THEN** no USDT rate or amount is invented.
