# Watchers Specification

## Purpose
Turn external notices into reviewable financial candidates.

## Scope
Email → Watcher → Parser → Deterministic Rules → Optional AI → Normalize → Deduplicate → Transaction.

## Business rules
Every stage MUST preserve replayability, quarantine failures, and provenance. Gmail OAuth MUST be readonly with encrypted refresh tokens, full initial sync, History API polling, stored history ID, and idempotent full resync on 404. Watch/PubSub is FUTURE only.

## Data model
Watcher source, raw message reference, parse result, rule evidence, normalized candidate, quarantine, and provenance.

## Constraints
Gmail is OPTIONAL; processing MUST work without it. Password collection is prohibited.

## Non-goals
Watch/PubSub activation and automatic mutation from ambiguous notices are non-goals.

## Requirements
### Requirement: Recoverable watcher pipeline
The system MUST replay a source item through the ordered pipeline without losing prior evidence.

#### Scenario: Invalid Gmail history cursor
GIVEN Gmail returns 404 for a stored history ID
WHEN polling resumes
THEN an idempotent full resync MUST be scheduled.

### Requirement: Binance Card parsing
The parser MUST match the observed sender `do-not-reply@ses.binance.com` and exact success subject pattern, recursively decode the observed UTF-8 base64 HTML, and parse the body grammar into amount, three-letter reported currency, and merchant. The UTC subject timestamp MUST be retained as event time and `Date` as notification/check metadata. Reported amount/currency MUST remain separate from settlement amount/currency. It MUST NOT equate reported USD with USDT based on card-use context; settlement amount/currency MUST remain unresolved and reviewable unless authoritative mapping or evidence resolves them. `Message-ID` MUST be retained as fallback deduplication. A hidden provider UUID MAY be retained only as a candidate and MUST remain UNVERIFIED as a stable semantic identity. Refunds, reversals, alternate currencies, and other template variants REQUIRES REAL SAMPLE.

#### Scenario: Unresolved USD notice
GIVEN a matching notice reports USD without authoritative settlement mapping
WHEN it is normalized
THEN it MUST remain reviewable without inventing USDT.

### Requirement: Banco Ganadero notification parsing
The parser MUST match sender `notificaciones@bg.com.bo`, decode RFC2047 subjects, and recursively decode observed nested multipart HTML with 7bit or quoted-printable transfer encoding. It MUST parse credit notices of the form `Recibiste Bs <amount> ... *<suffix>` and debit notices of the form `Enviaste Bs <amount> ... *<suffix>`, map the `Bs` token to BOB while preserving the raw token, and retain direction and masked suffix. It MUST NOT infer payee, glosa, bank transaction ID, or event time where absent. Header `Date` MUST be retained only as notification time, and `Message-ID` MUST be retained for deduplication. Trusted receiver authentication metadata MUST be preserved as provenance without claiming independent cryptographic verification. The candidate MUST enter Pending/review until a statement may enrich or match it.

#### Scenario: Banco Ganadero notice without event facts
GIVEN a Banco Ganadero debit or credit notice supplies only direction, amount, masked suffix, and header `Date`
WHEN it is normalized
THEN it MUST remain Pending/reviewable and MUST NOT treat notification time as event time.

### Requirement: BCP QR notification parsing
The parser MUST match the observed BCP QR sender and subject contract, recursively decode its HTML using the MIME charset in preference to conflicting inner metadata, and MUST safely fail to review when decoding is not reliable. It MUST retain transaction ID, receipt ID, body Fecha, origin/destination, beneficiary/bank, BOB amount, and raw glosa. Body Fecha MUST be event time; `-04:00` MAY be inferred only from a matching originating header and MUST retain its timezone provenance. Deduplication MUST prioritize transaction ID, then receipt ID, then `Message-ID`, while retaining every available identifier. The parser MUST preserve glosa and MUST NOT synthesize a missing glosa. Incoming, missing-glosa, different-ID, failure, refund, and template-variant behavior REQUIRES REAL SAMPLE.

#### Scenario: BCP QR conflicting charset metadata
GIVEN a BCP QR HTML part has a MIME charset that conflicts with inner metadata
WHEN it is decoded
THEN the MIME charset MUST take precedence, its provenance MUST be retained, and an unsafe decode MUST be sent to review.

## Acceptance criteria
The pipeline, 404 recovery, quarantine, replay, Binance currency protection, and Banco Ganadero and BCP QR evidence boundaries are documented.
