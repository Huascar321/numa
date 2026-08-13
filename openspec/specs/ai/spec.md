# AI Specification

## Purpose
Offer bounded, optional assistance without financial authority.

## Scope
OpenRouter/Groq settings, encrypted provider keys, and suggestions.

## Business rules
AI is OPTIONAL and MUST be enabled manually. Settings MUST select provider and model; no model is hardcoded. AI MAY suggest category, merchant, or glosa only. For BCP QR, it MAY suggest a category only from informative non-default raw glosa; it MUST NOT synthesize or overwrite raw glosa. It MUST NOT set money, account, timestamp, direction, or final transaction creation. Keys MUST be encrypted server-side. Output MUST pass local schema validation and SHOULD use strict output where supported.

## Data model
Provider setting, encrypted key reference, model selection, request provenance, schema result, and suggestion.

## Constraints
Deterministic use MUST remain functional when AI is disabled or fails.

## Non-goals
Autonomous financial mutations are non-goals.

## Requirements
### Requirement: Validated optional suggestions
The system MUST reject or quarantine invalid provider output.

#### Scenario: Provider unavailable
GIVEN AI is disabled or fails
WHEN a candidate is processed
THEN deterministic processing MUST continue without financial mutation.

### Requirement: Bounded BCP QR category suggestion
The system MUST make an AI category suggestion for BCP QR optional and reviewable. It MUST NOT generate one from missing glosa or from the common user-supplied `BM BM QR INTERBANCARIA` default, and it MUST preserve the observed `BM BM QR PAGO DE PRODUCTOS` and every other raw glosa unchanged.

#### Scenario: BCP QR missing or default glosa
GIVEN a BCP QR candidate has no glosa or has `BM BM QR INTERBANCARIA`
WHEN AI suggestions are generated
THEN no glosa is invented or overwritten and no category suggestion is generated from that value.

## Acceptance criteria
Settings, encrypted keys, bounded fields, and local validation are represented.
