# Watchers delta

## ADDED Requirements

### Requirement: Explicit fail-closed Gmail sender scope
Gmail collection MUST require a nonempty, validated allowlist of exact sender
mailbox addresses, normalized case-insensitively. Full sync, History polling
and 404 recovery MUST apply the same scope. The application MUST verify a
single unambiguous From mailbox and exclude SPAM/TRASH before requesting raw
MIME. Unmatched, missing, malformed, ambiguous or unavailable sender metadata
MUST NOT cause a body download or a stored message. Filtering MUST NOT be
represented as sender authentication or a narrowed Google authorization scope.

#### Scenario: Unrelated candidate in full sync or History
- **GIVEN** an enabled allowlist and a candidate with an unapproved From mailbox
- **WHEN** full sync or History processes the candidate
- **THEN** the raw message MUST NOT be downloaded or stored, while the page checkpoint can advance normally.

#### Scenario: Empty scope
- **GIVEN** no allowed senders are configured or persisted on a connection
- **WHEN** authorization or synchronization is attempted
- **THEN** collection MUST stop without a whole-mailbox fallback and financial operations MUST remain usable.

#### Scenario: Spam or trash
- **GIVEN** a candidate has an approved sender but is labelled SPAM or TRASH
- **WHEN** it is considered for ingestion
- **THEN** raw MIME MUST NOT be requested or stored.

### Requirement: Stable connection filter and visible collection scope
The application MUST persist the effective sender list on each authorized
connection and keep it stable across pages, retries, restarts and cursor recovery.
Changing server defaults MUST NOT silently alter an active connection.
Reconnecting the same mailbox MUST adopt the current configured list and
schedule a filtered full resync. Existing stored evidence MUST remain intact.
Connections migrated without an explicit scope MUST require reconnection before
further ingestion. The Gmail screen MUST show configured and effective senders
and explain that sender filtering does not restrict Google's mailbox-wide
readonly permission or identify transaction notices by their content.

#### Scenario: Defaults change during a scan
- **GIVEN** a paginated scan started with one approved sender list
- **WHEN** server defaults change before the next page or a worker restart
- **THEN** the connection MUST continue with its saved list until explicit reconnection.

#### Scenario: Reconnection with updated scope
- **GIVEN** an existing connection and a new configured sender list
- **WHEN** the same mailbox is reauthorized
- **THEN** the new list MUST be persisted, a filtered resync scheduled and previous evidence preserved without duplicates.

#### Scenario: Legacy connection
- **GIVEN** a connection created before explicit sender scoping
- **WHEN** the filter migration is applied
- **THEN** it MUST NOT resume ingestion until reauthorized with a nonempty scope.
