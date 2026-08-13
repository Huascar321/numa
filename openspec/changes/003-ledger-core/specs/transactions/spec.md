# Transactions delta

## ADDED Requirements

### Requirement: Protected Pending transaction classification
Every plan MUST have immutable nondeletable Pending, and uncategorized records MUST use it.

#### Scenario: Uncategorized expense
- **WHEN** an expense lacks a confirmed category
- **THEN** it is assigned to that plan's Pending category and remains correctable.

### Requirement: Provenance-preserving correction
Corrections MUST retain source metadata, prior values, and correction history.

#### Scenario: Edit imported merchant
- **WHEN** a user changes an imported merchant
- **THEN** the imported value and correction event remain reviewable.
