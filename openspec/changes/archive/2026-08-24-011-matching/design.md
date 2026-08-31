# Design

Use external ID, account, amount/currency, timestamp, merchant/memo, and bank
reference signals. Classify EXACT_MATCH, HIGH_CONFIDENCE_MATCH,
POSSIBLE_MATCH, or NEW_TRANSACTION. Only deterministic auditable exact/high
policy may link/enrich; possible matches never auto-merge. Manual values survive
statement enrichment. Bank notice candidates with no event timestamp remain
Pending until statement matching can provide an authoritative event fact.
Notification time is retained but never substituted for transaction time. BCP
QR matching prioritizes transaction ID, receipt ID, then `Message-ID`; all
available IDs are retained.
