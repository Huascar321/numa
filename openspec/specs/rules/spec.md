# Rules Specification

## Purpose
Apply deterministic, explainable automation before optional AI.

## Scope
Typed watcher and transaction normalization rules.

## Business rules
Rules MUST have typed inputs, stable order, explicit evidence, and replayable results. Conflicts MUST surface or quarantine; they MUST NOT be silently resolved.

## Data model
Rule: scope, predicate, ordered priority, action, version, and evidence result.

## Constraints
Rules MUST NOT overwrite protected manual fields or create ambiguous financial facts.

## Non-goals
Probabilistic AI decisions as deterministic rules are non-goals.

## Requirements
### Requirement: Deterministic rule execution
The system MUST record applied and skipped rule evidence.

#### Scenario: Conflicting rules
GIVEN two applicable rules with incompatible outcomes
WHEN they execute
THEN the candidate MUST be surfaced or quarantined.

### Requirement: Exact BCP QR subtype rules
Deterministic BCP QR subtype rules MAY act only on exact recognized raw glosa values, including the observed `BM BM QR PAGO DE PRODUCTOS` and the common user-supplied `BM BM QR INTERBANCARIA`. Rules MUST preserve raw glosa and MUST NOT synthesize `BM BM QR INTERBANCARIA` or any other glosa when it is absent.

#### Scenario: BCP QR glosa is absent
GIVEN a BCP QR candidate has no glosa
WHEN deterministic subtype rules run
THEN no glosa or subtype MUST be invented and the candidate MUST remain reviewable.

## Acceptance criteria
Rule order, evidence, and replay are available for review.
