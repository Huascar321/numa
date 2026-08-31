# Design

The watcher matches the observed provider sender and exact success subject
pattern, decodes UTF-8 base64 `text/html`, and parses the deterministic body
sentence into amount, three-letter reported currency, and merchant. The UTC
subject timestamp is event time; `Date` is notification/consistency metadata;
`Message-ID` is fallback deduplication. A hidden provider UUID is only a
candidate identity and remains **UNVERIFIED** for semantic stability.

Reported amount/currency remain distinct from settlement amount/currency. User
context that the card is used for USDT transactions does not authorize a USD to
USDT conversion. Settlement may be resolved only with authoritative account
mapping or settlement evidence plus explicit deterministic configuration or
review; a generic rule cannot equate reported USD to USDT. Unresolved settlement
creates a reviewable candidate. Refunds, reversals, alternate currencies, other
templates, and authoritative USDT settlement evidence **REQUIRES REAL SAMPLE**.
