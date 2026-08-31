# Design

Use authorization-code/server OAuth with the minimum Gmail readonly scope and
encrypted server refresh tokens. Perform initial full sync, then scheduled
History API polling with stored historyId; 404 schedules full resync. Gmail
Watch/PubSub is OPTIONAL and never the sole reliability mechanism. Observed
watcher sources require recursive MIME traversal, transfer-decoding, RFC2047
header decoding, and MIME charset precedence over conflicting inner metadata,
with safe fallback and review. Provider-specific parsers retain notification
metadata separately from event facts and preserve authentication outcomes as
provenance; the watcher does not independently claim signature verification.
