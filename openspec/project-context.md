# Numa project context

## Product decisions
Numa is a personal, deterministic-first, AI-assisted, human-correctable finance PWA. It MUST work without AI, Gmail, or an exchange provider. Plans are independent; each has one reporting and budget currency. BOB and USDT are initial, extensible currencies. Amounts are exact decimals or integer atoms, never floats. Server state is authoritative; offline use is safe only through an idempotent outbox.

## Domain glossary and invariants
- **Plan:** independent financial workspace with categories, accounts, reporting currency, and budget.
- **Account:** Bank, Cash, Wallet, Credit Card, Crypto, or Other; balances are derived from ledger movements.
- **Transaction:** income, expense, transfer, or reconciliation adjustment. `Pending` is an immutable per-plan category; `cleared` does not exist.
- **Transfer:** atomically linked legs; excluded from income, expense, and budget activity.
- **Provenance:** retained source data, source order, corrections, and enrichments; ambiguity stops automated financial mutation.
- **Quote:** explicit source, time, side, formula, and context; no silent FX aggregation.

## Phase map
001 foundation; 002 accounts; 003 ledger and initial budgeting; 004 transfers; 005 budget engine; 006 reconciliation; 007 Gmail; 008 Binance Card; 009 watchers/rules; 010 statements; 011 matching; 012 AI; 013 automation suggestions; 014 analytics; 015 exchange rates; 016 MCP; 017 polish.

## Research snapshot — 2026-08-12
Official references, subject to current-version changes: [React](https://react.dev/), [Vite](https://vite.dev/), [FastAPI](https://fastapi.tiangolo.com/), [PostgreSQL](https://www.postgresql.org/docs/), [Gmail API](https://developers.google.com/gmail/api), [Workbox](https://developer.chrome.com/docs/workbox/), [MCP](https://modelcontextprotocol.io/), [OpenRouter](https://openrouter.ai/docs), [Groq](https://console.groq.com/docs). Product versions are target decisions: React 19, Vite 8, PostgreSQL 18; validate compatibility at implementation time. Binance P2P endpoint status is UNVERIFIED.

## Observed source evidence — 2026-08-12
- Binance Card success notices are observed from `do-not-reply@ses.binance.com` as UTF-8 base64 HTML. Their UTC subject timestamp is the event time; `Date` is notification/check metadata. The body reports amount, a three-letter reported currency, and merchant. The observed USD report remains USD; user context that the card is used for USDT does not establish settlement amount or currency. `Message-ID` is fallback deduplication; a hidden provider UUID is UNVERIFIED as a stable semantic identity. Refunds, reversals, alternate currencies, template variants, and authoritative USDT settlement evidence REQUIRES REAL SAMPLE.
- Banco Ganadero credit/debit notices are observed from `notificaciones@bg.com.bo` with RFC2047 subjects and nested HTML multipart bodies using 7bit or quoted-printable transfer encoding. They provide only direction, a `Bs` amount mapped to BOB, and a masked suffix; header `Date` is notification time, not event time. Trusted receiver authentication metadata is retained as provenance without claiming independent cryptographic verification.
- BCP QR notices provide transaction/receipt IDs, body event date, parties, beneficiary/bank, BOB amount, and glosa. MIME charset takes precedence over conflicting inner metadata; `-04:00` is inferred only from a matching originating header and retains timezone provenance. The common user-supplied glosa is `BM BM QR INTERBANCARIA`; the observed sample is `BM BM QR PAGO DE PRODUCTOS`.
- Four consecutive Banco Ganadero CSV months for one account verify stable UTF-8 BOM, CRLF, semicolon, preamble/header/footer, period chain, debit/credit counts, and running arithmetic. `SALDO ACTUAL` is current/as-of-export, not period ending. Additional account/export versions and embedded-semicolon, escaped-quote, or multiline variants REQUIRES REAL SAMPLE.
