# Watchers delta

## ADDED Requirements

### Requirement: Recoverable Gmail synchronization
Gmail MUST use encrypted server refresh tokens, initial full sync, History polling, stored historyId, and full resync on 404.

#### Scenario: Invalid history cursor
- **WHEN** Gmail returns 404 for historyId
- **THEN** a full resync is scheduled idempotently without accepting a password.

### Requirement: Recursive email decoding
Email watcher parsing MUST recursively traverse nested MIME parts, decode
transfer encodings, decode RFC2047 headers, and prefer the MIME charset over
conflicting inner metadata, with safe fallback and review on failure.

#### Scenario: Nested encoded notice
- **GIVEN** a notice contains nested multipart content and a transfer-encoded HTML part
- **WHEN** it is parsed
- **THEN** the decoded provider fields and charset provenance remain reviewable.
