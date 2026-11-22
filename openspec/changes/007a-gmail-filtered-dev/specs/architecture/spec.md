# Architecture delta

## ADDED Requirements

### Requirement: Isolated local development database and ports
Local development MUST use a PostgreSQL 18 database, Compose project and volume
separate from the test database and from other projects. Its exposed port MUST
bind only to loopback, use a non-common configurable default and be checked for
availability before launch. Startup MUST NOT reset existing databases or change
the test service. Server credentials MUST remain in ignored local configuration.
The web proxy MUST support the chosen local API port without exposing secrets.
The documented web URL MUST match the registered OAuth callback; any change to
that callback MUST be explicit rather than a silent port fallback.

#### Scenario: Development and tests run together
- **GIVEN** the existing PostgreSQL test service is already running
- **WHEN** the development stack starts
- **THEN** the two stacks MUST use different ports and volumes, and migrations MUST affect only the configured development database.

#### Scenario: Port collision
- **GIVEN** a chosen development port is occupied
- **WHEN** startup is attempted
- **THEN** startup MUST report the conflict without stopping the unrelated service or silently changing the OAuth web origin.

#### Scenario: Local stack ready without Gmail authorization
- **GIVEN** local development configuration and the stored OAuth client settings
- **WHEN** migrations, API, worker and web are started
- **THEN** readiness and proxied API access MUST work without authorizing a real Google account, downloading messages or creating financial transactions.
