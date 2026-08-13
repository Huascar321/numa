# Exchange rates delta

## ADDED Requirements

### Requirement: No implicit reported-currency conversion
Reported card currency MUST remain distinct from any settlement quote until
authoritative account mapping or settlement evidence plus explicit deterministic
configuration or review resolves it. A generic rule alone MUST NOT equate
reported USD to USDT.

#### Scenario: USD notice
- **WHEN** a notice reports USD without settlement evidence
- **THEN** no USDT rate or amount is invented.
