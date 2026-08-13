# Deduplication Specification

## Purpose
Classify overlap across manual, watcher, and statement sources without data loss.

## Scope
Candidate matching and safe enrichment.

## Business rules
Sources are manual, watcher, and statement. Signals MUST be documented. Classification MUST be EXACT_MATCH, HIGH_CONFIDENCE_MATCH, POSSIBLE_MATCH, or NEW_TRANSACTION. Ambiguous matches MUST NOT merge destructively. Enrichment MUST preserve manual fields and all provenance.

## Data model
Candidate source, compared signals, classification, linked transaction, enrichment fields, and provenance chain.

## Constraints
Matching MUST be reviewable and non-destructive.

## Non-goals
Auto-merging POSSIBLE_MATCH is a non-goal.

## Requirements
### Requirement: Auditable classification
The system MUST retain the signals supporting each classification.

#### Scenario: Possible match
GIVEN similar but inconclusive signals
WHEN matching runs
THEN it MUST remain separate for review.

### Requirement: Provider identifier precedence
Deduplication MUST retain all available provider identifiers and apply provider-specific precedence without discarding provenance. Binance Card MUST use `Message-ID` as fallback deduplication, because a hidden provider UUID is UNVERIFIED as a stable semantic identity. BCP QR MUST prioritize transaction ID, then receipt ID, then `Message-ID`. Banco Ganadero notifications MUST use `Message-ID` and remain separate and reviewable when their limited notice facts cannot establish a match.

#### Scenario: BCP QR has transaction and receipt IDs
GIVEN a BCP QR candidate contains both transaction ID and receipt ID
WHEN deduplication runs
THEN it MUST use transaction ID before receipt ID and retain both identifiers in provenance.

### Requirement: Banco Ganadero statement enrichment
A Banco Ganadero notification candidate MAY be enriched only by an auditable statement match. Enrichment MAY add statement payee, glosa, bank transaction ID, and event time, but MUST preserve raw notice fields, notification time, and provenance. It MUST NOT infer an event time from the notice header when matching remains inconclusive.

#### Scenario: Inconclusive Banco Ganadero notice match
GIVEN a Banco Ganadero notice has only notification time and matching is inconclusive
WHEN enrichment runs
THEN it MUST remain separate and reviewable without an inferred transaction event time.

## Acceptance criteria
All four classes and manual/provenance preservation are enforced.
