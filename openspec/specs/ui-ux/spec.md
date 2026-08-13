# UI/UX Specification

## Purpose
Define the personal PWA navigation and mobile-safe interaction model.

## Scope
Monochrome reference direction, responsive PWA navigation, installation education, and permission boundaries.

## Business rules
Primary navigation MUST be Home, Transactions, Plan, Analytics, and More. More MUST list Accounts, Goals, Statements, Pending, Watchers, Automation Suggestions, Categories, Tags, and Settings. UI SHOULD follow the monochrome reference direction. It MUST support iOS safe areas, `dvh`, and VisualViewport. Installation education MUST be manual. Push is OPTIONAL for installed iOS 16.4+; background sync and location are not used. Geolocation is OPTIONAL and requires explicit consent.

## Data model
Navigation state, installation education state, permission state, and stale-cache indicator.

## Constraints
Offline cached finance data MUST be labeled stale; unsupported writes MUST NOT appear committed.

## Non-goals
Background sync, passive location collection, and automatic install prompts are non-goals.

## Requirements
### Requirement: Exact responsive navigation
The application MUST expose the specified primary and More navigation items.

#### Scenario: Offline cached view
GIVEN the network is unavailable
WHEN cached finance data is displayed
THEN it MUST be labeled stale and unsupported writes MUST not be presented as committed.

## Acceptance criteria
Navigation, iOS viewport handling, manual installation education, and permission limits are specified.
