# Watchers delta

## ADDED Requirements

### Requirement: Unresolved Binance Card currency
The watcher MUST match the observed provider sender and exact success subject
pattern, recursively decode the UTF-8 base64 HTML sample, and preserve reported
amount/currency separately from settlement amount/currency. It MUST NOT assume
reported USD is USDT or allow a generic rule alone to resolve settlement.
Settlement may be resolved only with authoritative account mapping or settlement
evidence plus explicit deterministic configuration or review. The subject
timestamp is event time; `Date` is notification time; `Message-ID` is fallback
deduplication. A hidden provider UUID remains **UNVERIFIED** as a stable semantic
identity.

#### Scenario: Settlement asset unresolved
- **WHEN** authoritative account mapping or settlement evidence plus explicit
  deterministic configuration or review is absent
- **THEN** the candidate remains unresolved and reviewable.

## Evidence

The observed success-template sender, subject, MIME, and event-time contract are
resolved. Refunds, reversals, alternate currencies, other template variants,
and authoritative USDT settlement evidence **REQUIRES REAL SAMPLE**.
