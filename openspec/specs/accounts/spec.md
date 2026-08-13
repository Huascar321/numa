# Accounts Specification

## Purpose
Manage independent-plan account registries with currencies, lifecycle, and
derived balances that preserve plan boundaries.

## Scope
Bank, Cash, Wallet, Credit Card, Crypto, and Other accounts with extensible currencies including BOB and USDT.

## Business rules
Each account MUST belong to one Plan and have one currency. Balances MUST be derived, not entered. A Plan MUST have one reporting/budget currency and MUST NOT silently aggregate unconverted currencies.

## Data model
Account: plan, type, name, currency, lifecycle, and derived balance.

## Constraints
Archived accounts MUST retain readable history and reject new postings.

## Non-goals
Shared accounts and multi-plan accounts are non-goals.

## Requirements
### Requirement: Plan-scoped account registry
The system MUST store account type, currency, and lifecycle in its Plan.

#### Scenario: Archive historical account
GIVEN an account with posted history
WHEN it is archived
THEN history MUST remain readable and new postings MUST be blocked.

## Acceptance criteria
All six account types and derived balances are supported.
