# Exchange Rates Specification

## Purpose
Represent explicit exchange quotes without assumed rates.

## Scope
Manual BOB/USDT quotes and OPTIONAL provider adapters.

## Business rules
`BUY_USDT = BOB paid / USDT received`; `SELL_USDT = BOB received / USDT sold`. Quotes MUST retain side, offer context, source, and observation time. A manual quote MUST be available. No 6.96 rate is primary. The official Binance P2P endpoint is UNVERIFIED; an auto adapter is OPTIONAL and MUST NOT be the sole source. Unavailable or stale state MUST be explicit.

## Data model
Quote: base/quote currencies, side, exact amounts/rate, offer context, source, observed time, and freshness.

## Constraints
No implicit conversion or silent aggregation is permitted.

## Non-goals
Guaranteed provider availability and exchange execution are non-goals.

## Requirements
### Requirement: Contextual explicit quote
The system MUST preserve quote formula and freshness.

#### Scenario: Manual BUY_USDT quote
GIVEN BOB paid and USDT received
WHEN a manual quote is saved
THEN its rate MUST equal BOB paid divided by USDT received.

## Acceptance criteria
Both formulas, manual entry, and explicit stale/unavailable state are represented.
